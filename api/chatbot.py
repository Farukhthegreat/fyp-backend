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
                farm_name = farm.farm_name or ''
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
            # gemini-2.5-flash has the best free-tier RPD (1500/day) and
            # strong Urdu support. flash-lite is faster but weaker; pro is
            # overkill and counted against a much lower daily cap.
            response = _CLIENT.models.generate_content(
                model='gemini-2.5-flash',
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
