"""
AvianVet — Gemini-backed conversational assistant.

Exposes POST /api/assistant/ that takes a user message + recent history
and returns a veterinarian-style reply. Keeps the API key server-side,
injects per-user context (latest diagnosis + farm) into the system prompt,
and hard-caps history length so a single misuser can't blow the token
budget.

Uses the `google-genai` SDK (successor to `google-generativeai`). The older
SDK pins an incompatible protobuf range that collides with Firebase Admin's
grpcio-status on Render.
"""

import logging
import os
import re
import time

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DiagnosisResult, Farm

logger = logging.getLogger(__name__)

# google.genai is imported lazily on first use. Importing at module load
# adds ~2-5s to Django's URL-config boot, which on Render's sync gunicorn
# pushes past the port-detection timeout on cold deploys.
_CLIENT = None
_GENAI_TYPES = None
_GENAI_ERROR: str | None = None


def _ensure_client() -> bool:
    global _CLIENT, _GENAI_TYPES, _GENAI_ERROR
    if _CLIENT is not None:
        return True
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        _GENAI_ERROR = 'GEMINI_API_KEY is not configured'
        return False
    try:
        from google import genai  # noqa: WPS433 — lazy by design
        from google.genai import types as genai_types  # noqa: WPS433
        _CLIENT = genai.Client(api_key=api_key)
        _GENAI_TYPES = genai_types
        return True
    except Exception as e:  # noqa: BLE001
        _GENAI_ERROR = f'Gemini client init failed: {e}'
        logger.exception('Gemini client init failed')
        return False


# Bounded so a pathological client can't feed the model an unbounded
# transcript — the free tier has generous per-minute token limits but we
# still pay (in latency) for every token we send.
MAX_HISTORY_TURNS = 20
MAX_MESSAGE_CHARS = 2000


# Belt-and-braces sanitiser for model replies. The system prompt tells
# Gemini to avoid markdown, but the model occasionally slips one in. We
# strip the common emphasis wrappers so the client never shows literal
# asterisks / underscores / backticks to a farmer who can't read them.
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*', re.DOTALL)
_MD_ITAL = re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', re.DOTALL)
_MD_UNDER = re.compile(r'__(.+?)__', re.DOTALL)
_MD_ITAL_U = re.compile(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', re.DOTALL)
_MD_HEADING = re.compile(r'^\s{0,3}#{1,6}\s+', re.MULTILINE)
_MD_BACKTICK = re.compile(r'`([^`]+)`')


# Gemini model fallback chain. Each entry has its own free-tier quota
# bucket, so a 429 on one model does not block the next. Defense-day
# ordering puts the freshest, least-touched buckets first (3.x previews
# and 2.5-pro) so chat answers fast even when the workhorse 2.5/2.0
# tiers are exhausted from earlier traffic. Verified against
# `models.list` on the project's API key — preview names need the
# `-preview` suffix or the API returns 404.
_GEMINI_FALLBACK_MODELS = (
    'gemini-3.1-flash-lite-preview',
    'gemini-3-flash-preview',
    'gemini-2.5-pro',
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash',
)

# Per-model "exhausted until" cache. When a model returns 429 /
# RESOURCE_EXHAUSTED we record a cooldown timestamp and the fallback
# walker skips it on subsequent calls until the cooldown expires.
# This eliminates wasted retries through known-dead models — the
# difference between a 15s response (walking past 3 dead models) and
# a sub-2s response that goes straight to the live one. Cooldown is
# kept short so a quota reset is picked up automatically without a
# server restart.
_QUOTA_COOLDOWN_SECONDS = int(os.environ.get('GEMINI_QUOTA_COOLDOWN', '900'))
_EXHAUSTED_UNTIL: dict[str, float] = {}


def _is_exhausted(model: str) -> bool:
    expiry = _EXHAUSTED_UNTIL.get(model)
    return expiry is not None and time.time() < expiry


def _mark_exhausted(model: str) -> None:
    _EXHAUSTED_UNTIL[model] = time.time() + _QUOTA_COOLDOWN_SECONDS


def _generate_with_fallback(*, contents, config):
    """Call generate_content against each model in order until one
    doesn't raise a transient `5xx UNAVAILABLE` error. Other exceptions
    bubble up immediately so genuine bugs (auth, schema, quota-exhaust)
    aren't masked. Returns the first successful response object.
    """
    last_exc = None
    for model in _GEMINI_FALLBACK_MODELS:
        if _is_exhausted(model):
            continue
        try:
            return _CLIENT.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ), model
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            quota_hit = (
                ' 429 ' in f' {msg} '
                or 'RESOURCE_EXHAUSTED' in msg
                or 'quota' in msg.lower()
            )
            transient = (
                ' 503 ' in f' {msg} '
                or 'UNAVAILABLE' in msg
                or '500 INTERNAL' in msg
                or 'overloaded' in msg.lower()
                or quota_hit
                # 404 NOT_FOUND / INVALID_ARGUMENT happen when a
                # preview model is renamed or retired. Skip the dead
                # name and let the chain reach a stable fallback
                # instead of crashing the whole request.
                or ' 404 ' in f' {msg} '
                or 'NOT_FOUND' in msg
                or 'is not found' in msg.lower()
                or 'INVALID_ARGUMENT' in msg
            )
            if quota_hit:
                _mark_exhausted(model)
            last_exc = exc
            if not transient:
                raise
            logger.warning(
                'Gemini %s unavailable (%s) — falling back', model, msg[:160],
            )
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('No Gemini fallback succeeded')


def _strip_markdown(text: str) -> str:
    if not text:
        return text
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_UNDER.sub(r'\1', text)
    text = _MD_ITAL.sub(r'\1', text)
    text = _MD_ITAL_U.sub(r'\1', text)
    text = _MD_HEADING.sub('', text)
    text = _MD_BACKTICK.sub(r'\1', text)
    return text


# The system prompt tells Gemini not to tack on follow-up question
# suggestions, but the model sometimes ignores that. Cut any trailing
# section that starts with a giveaway phrase so the client only ever sees
# the actual answer — the UI has its own suggestion chips on the empty
# state that duplicate this noise visually.
_FOLLOWUP_PATTERNS = re.compile(
    r'\n\s*(?:'
    r'(?:you\s+(?:might|could|can|may)\s+(?:also\s+)?ask|'
    r'(?:here\s+are\s+)?(?:some\s+)?(?:related|other|follow[- ]?up|similar)\s+questions?|'
    r'try\s+asking|want\s+to\s+know\s+more|if\s+you.?(?:re|d)\s+curious|'
    r'would\s+you\s+like\s+to\s+(?:know|ask)|'
    r'کچھ\s+اور\s+سوالات|مزید\s+سوالات|آپ\s+یہ\s+بھی\s+پوچھ\s+سکتے)'
    r'[^\n]*(?:\n.*)?$)',
    re.IGNORECASE | re.DOTALL,
)


def _strip_followup_suggestions(text: str) -> str:
    if not text:
        return text
    return _FOLLOWUP_PATTERNS.sub('', text).rstrip()


def _build_system_prompt(farm_name: str, last_diagnosis: dict | None) -> str:
    """
    Craft a system prompt that anchors the model as a Pakistani poultry
    veterinarian. Injects the farmer's farm name and latest diagnosis so
    answers feel personalised. Bilingual instruction lets the farmer write
    Urdu or English without a mode switch.
    """
    lines = [
        "You are an expert poultry care helper assisting a farmer in Pakistan.",
        "",
        "RULES:",
        "- Reply in the same language the farmer uses (Urdu or English). Detect per-message.",
        "- Keep answers under 120 words unless the farmer asks for more detail.",
        "- Use simple, plain language. No jargon unless explaining it.",
        "- Never prescribe human medicine. Only poultry-safe drugs, and always suggest consulting a qualified local vet before administering.",
        "- If the farmer asks about disease symptoms, be concrete: list 3-5 signs, cause, and 2-3 practical actions.",
        "- If asked about unrelated topics (politics, entertainment), politely redirect to poultry care.",
        "- If the farmer writes Urdu, reply in Urdu script. If English, reply in English.",
        "- CRITICAL formatting rule: never use markdown. Do NOT output asterisks (**), underscores (__), backticks, or heading marks (#). Do not bold, italicize, or code-format anything. The client renders plain text — markdown syntax will appear literally and looks broken.",
        "- For lists, use a simple line-break with a short dash: '- item'. Don't use nested bullets.",
        "- Keep sentences short. One idea per line when listing steps.",
        "- NEVER suggest follow-up questions at the end of your answer. Do not write 'You might also ask:', 'Try asking:', 'Some related questions:', or list alternative questions. The client provides its own suggestion UI. Always end with your direct answer and nothing else.",
        "- Do NOT echo or rephrase the user's question back before answering. Start with the answer directly.",
    ]
    if farm_name:
        lines.append(f"\nFARMER CONTEXT:\n- Farm name: {farm_name}")
    if last_diagnosis:
        disease = last_diagnosis.get('disease_name') or 'Unknown'
        confidence = last_diagnosis.get('confidence') or 0
        lines.append(
            f"- Most recent diagnosis: {disease} (confidence {round(float(confidence), 1)}%)"
        )
        lines.append(
            "  If the farmer asks about their latest result, refer to this diagnosis."
        )
    return '\n'.join(lines)


def _history_to_contents(raw_history):
    """
    Convert the client-provided history (list of {role, text}) into the
    typed `Content` objects the new SDK expects. Drops malformed entries
    and truncates to the last MAX_HISTORY_TURNS turns.
    """
    if not isinstance(raw_history, list):
        return []
    contents = []
    for entry in raw_history[-MAX_HISTORY_TURNS:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get('role')
        text = entry.get('text')
        if role not in ('user', 'model'):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        contents.append(
            _GENAI_TYPES.Content(
                role=role,
                parts=[_GENAI_TYPES.Part.from_text(text=text[:MAX_MESSAGE_CHARS])],
            )
        )
    return contents


class ChatbotView(APIView):
    """
    POST /api/assistant/

    Body:
      {
        "message": "free text from farmer",
        "history": [{"role": "user|model", "text": "..."}]    # optional
      }

    Response:
      { "reply": "<model text>" }   # 200

    Errors:
      503 if GEMINI_API_KEY is missing / configure failed.
      400 if message is empty.
      502 on upstream Gemini errors (rate limit, quota, network).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _ensure_client():
            logger.error('Gemini not configured: %s', _GENAI_ERROR)
            return Response(
                {'error': 'assistant_unavailable'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        message = (request.data.get('message') or '').strip()
        if not message:
            return Response(
                {'error': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[:MAX_MESSAGE_CHARS]

        # Pull personalisation context. Swallow failures so a missing farm
        # record never blocks the assistant — the model just answers without
        # per-user anchoring.
        farm_name = ''
        last_diagnosis = None
        try:
            farm = Farm.objects.filter(user=request.user).first()
            if farm:
                farm_name = farm.name or ''
        except Exception:  # noqa: BLE001
            logger.warning('Chatbot context: farm lookup failed', exc_info=True)
        try:
            diag = (
                DiagnosisResult.objects
                .filter(user=request.user)
                .order_by('-created_at')
                .first()
            )
            if diag:
                last_diagnosis = {
                    'disease_name': diag.disease_name,
                    'confidence': float(diag.confidence or 0),
                }
        except Exception:  # noqa: BLE001
            logger.warning('Chatbot context: diagnosis lookup failed', exc_info=True)

        system_prompt = _build_system_prompt(farm_name, last_diagnosis)

        # Build the full conversation turn list: prior history plus the new
        # user message tacked on at the end.
        contents = _history_to_contents(request.data.get('history'))
        contents.append(
            _GENAI_TYPES.Content(
                role='user',
                parts=[_GENAI_TYPES.Part.from_text(text=message)],
            )
        )

        try:
            # 2.5-flash is the headline model but its free-tier slot is
            # often 503 during peak hours; _generate_with_fallback walks
            # to flash-lite then 2.0-flash so chats keep working.
            response, _model = _generate_with_fallback(
                contents=contents,
                config=_GENAI_TYPES.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    top_p=0.9,
                    max_output_tokens=512,
                ),
            )
            reply = (getattr(response, 'text', None) or '').strip()
            if not reply:
                return Response(
                    {'error': 'empty_reply'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            reply = _strip_markdown(reply)
            reply = _strip_followup_suggestions(reply)
            return Response({'reply': reply})
        except Exception as e:  # noqa: BLE001
            # Upstream retryable errors (quota, transient, bad key) bubble
            # up as 429 / 403 / etc. Map to 502 so the Flutter retry path
            # engages instead of showing a generic server error. Surface
            # the exception class + message so operators can diagnose
            # key/quota issues from the client without tailing logs.
            logger.exception('Gemini call failed')
            return Response(
                {
                    'error': 'upstream_error',
                    'error_type': type(e).__name__,
                    'detail': str(e)[:400],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


# --------------------------------------------------------------------------
# XAI explanation view
# --------------------------------------------------------------------------

# Gemini vision call gets the cropped poultry sample + the model's picked
# class and writes a short, farmer-friendly explanation of *which visual
# patterns* (colour, texture, blood traces, shape, etc.) drove the call.
# This replaces the raw heatmap as the primary XAI artefact — the heatmap
# didn't localise the way farmers expected, so a plain-text doctor-style
# explanation builds trust better.


_XAI_SYSTEM = (
    "You are an expert poultry veterinarian writing a short XAI note for "
    "a Pakistani farmer. Look at the cropped photo of chicken faeces and "
    "describe the visible evidence — colour, texture, consistency, blood "
    "traces, mucus, chalky streaks, frothy appearance, shape, undigested "
    "feed. Tie observations to the predicted class. Never invent symptoms "
    "not visible. If the prediction is Healthy, say why the sample looks "
    "normal. If the image clearly does not match the predicted class, "
    "say so honestly. Speak as if you examined the sample yourself; do "
    "not say 'the AI' or 'the model'. No markdown, no asterisks, no "
    "headings, no code fences."
)


def _xai_prompt(disease_name: str, confidence: float,
                probabilities: dict, language: str) -> str:
    runners = ''
    if isinstance(probabilities, dict) and probabilities:
        top = sorted(
            ((k, float(v)) for k, v in probabilities.items()
             if isinstance(v, (int, float))),
            key=lambda kv: -kv[1],
        )[:3]
        runners = ', '.join(f'{k} {v:.1f}%' for k, v in top)
    lang_hint = 'Urdu' if language == 'ur' else 'English'
    # Plain-text two-section format. Avoids JSON parsing fragility on
    # free-tier vision calls. The XAI handler splits on EXPLANATION: /
    # NOTE: headers — robust against extra whitespace or stray words.
    return (
        f"Predicted class: {disease_name} (confidence {confidence:.1f}%).\n"
        f"Top probabilities: {runners or 'n/a'}.\n"
        f"Write everything in {lang_hint}.\n\n"
        "Output EXACTLY two sections separated by the headers below. No "
        "other text outside these two sections.\n\n"
        "EXPLANATION:\n"
        "<60-120 words. One intro sentence on visible evidence, then 2-3 "
        "specific observations prefixed with `- `, then one closing line "
        "on what this means for the flock.>\n\n"
        "NOTE:\n"
        "<Short 1-2 sentence treatment log. Plain-language diagnosis line "
        "plus the single most urgent next step. Mention the drug name + "
        "dosing window only when applicable. Under 220 characters.>"
    )


class XaiExplainView(APIView):
    """
    POST /api/xai-explain/

    Body (JSON):
      {
        "disease_name": "Coccidiosis",
        "confidence": 87.4,
        "all_probabilities": {"Healthy": 5.2, "Coccidiosis": 87.4, ...},
        "image_data_url": "data:image/jpeg;base64,...",   # required
        "language": "en" | "ur"                            # optional, default "en"
      }

    Response:
      {
        "explanation": "The sample shows dark, watery stools with fine "
                       "red-brown streaks...",
        "language": "en"
      }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import base64

        if not _ensure_client():
            return Response(
                {'error': 'assistant_unavailable'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        disease_name = (request.data.get('disease_name') or '').strip()
        if not disease_name:
            return Response(
                {'error': 'disease_name is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            confidence = float(request.data.get('confidence') or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        language = (request.data.get('language') or 'en').strip().lower()
        if language not in ('en', 'ur'):
            language = 'en'

        image_data_url = request.data.get('image_data_url') or ''
        if not isinstance(image_data_url, str) or not image_data_url.startswith('data:image'):
            return Response(
                {'error': 'image_data_url is required (data:image/...;base64,...)'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            header, b64 = image_data_url.split(',', 1)
            mime = 'image/jpeg'
            if 'image/png' in header:
                mime = 'image/png'
            image_bytes = base64.b64decode(b64)
        except Exception:
            return Response(
                {'error': 'invalid image_data_url'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        probabilities = request.data.get('all_probabilities') or {}
        if not isinstance(probabilities, dict):
            probabilities = {}

        user_text = _xai_prompt(disease_name, confidence, probabilities, language)

        try:
            # Bake the system instruction into the user message instead of
            # using the dedicated `system_instruction` config field —
            # gemini-2.5-flash on the free tier sometimes ignores the
            # system instruction when an image is attached, which was
            # producing empty .text responses on every XAI call.
            full_prompt = f"{_XAI_SYSTEM}\n\n{user_text}"
            response, _model = _generate_with_fallback(
                contents=[
                    _GENAI_TYPES.Content(
                        role='user',
                        parts=[
                            _GENAI_TYPES.Part.from_bytes(
                                data=image_bytes, mime_type=mime,
                            ),
                            _GENAI_TYPES.Part.from_text(text=full_prompt),
                        ],
                    ),
                ],
                config=_GENAI_TYPES.GenerateContentConfig(
                    temperature=0.4,
                    top_p=0.9,
                    max_output_tokens=700,
                ),
            )

            raw = (getattr(response, 'text', None) or '').strip()
            # SDK occasionally puts content only in candidates[*].parts.
            if not raw:
                try:
                    for cand in getattr(response, 'candidates', None) or []:
                        content = getattr(cand, 'content', None)
                        if not content:
                            continue
                        for part in getattr(content, 'parts', None) or []:
                            text = getattr(part, 'text', None)
                            if text:
                                raw = text.strip()
                                break
                        if raw:
                            break
                except Exception:
                    pass

            if not raw:
                # Surface the prompt-feedback safety verdict so we can see
                # whether the model blocked the image instead of silently
                # returning empty.
                fb = getattr(response, 'prompt_feedback', None)
                logger.warning(
                    'Gemini XAI empty response (lang=%s, disease=%s, feedback=%r)',
                    language, disease_name, fb,
                )
                return Response(
                    {'error': 'empty_reply'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Two-section parse: split on EXPLANATION:/NOTE: headers.
            explanation = ''
            farmer_note = ''
            m = re.search(
                r'EXPLANATION\s*:\s*(.*?)(?:\n\s*NOTE\s*:\s*(.*))?$',
                raw,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if m:
                explanation = (m.group(1) or '').strip()
                farmer_note = (m.group(2) or '').strip()
            else:
                # Fallback — model ignored the headers. Use the whole body
                # as the explanation so the user still sees something.
                explanation = raw

            if not explanation:
                explanation = raw

            explanation = _strip_markdown(explanation)
            farmer_note = _strip_markdown(farmer_note) if farmer_note else ''
            # Trim trailing artefacts like "EXPLANATION:" leaking through.
            explanation = re.sub(r'^EXPLANATION\s*:\s*', '', explanation, flags=re.IGNORECASE)
            farmer_note = re.sub(r'^NOTE\s*:\s*', '', farmer_note, flags=re.IGNORECASE)
            return Response({
                'explanation': explanation,
                'farmer_note': farmer_note,
                'language': language,
            })
        except Exception as e:  # noqa: BLE001
            logger.exception('Gemini XAI call failed')
            return Response(
                {
                    'error': 'upstream_error',
                    'error_type': type(e).__name__,
                    'detail': str(e)[:400],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
