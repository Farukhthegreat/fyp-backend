"""
AvianVet — Gemini-backed conversational assistant.

Exposes POST /api/assistant/ that takes a user message + recent history
and returns a veterinarian-style reply. Keeps the API key server-side,
injects per-user context (latest diagnosis + farm) into the system prompt,
and hard-caps history length so a single misuser can't blow the token
budget.
"""

import logging
import os

import google.generativeai as genai
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DiagnosisResult, Farm

logger = logging.getLogger(__name__)

# Configured lazily so a missing key doesn't crash import at boot — the
# endpoint returns a 503 with a clear message instead.
_GENAI_READY = False
_GENAI_ERROR = None


def _ensure_genai_configured():
    global _GENAI_READY, _GENAI_ERROR
    if _GENAI_READY:
        return True
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        _GENAI_ERROR = 'GEMINI_API_KEY is not configured'
        return False
    try:
        genai.configure(api_key=api_key)
        _GENAI_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        _GENAI_ERROR = f'Gemini configure failed: {e}'
        logger.exception('Gemini configure failed')
        return False


# Bounded so a pathological client can't feed the model an unbounded
# transcript — the free tier has generous per-minute token limits but we
# still pay (in latency) for every token we send.
MAX_HISTORY_TURNS = 20
MAX_MESSAGE_CHARS = 2000


def _build_system_prompt(farm_name: str, last_diagnosis: dict | None) -> str:
    """
    Craft a system prompt that anchors the model as a Pakistani poultry
    veterinarian. Injects the farmer's farm name and latest diagnosis so
    answers feel personalised. Bilingual instruction lets the farmer write
    Urdu or English without a mode switch.
    """
    context_lines = [
        "You are AvianVet, an expert poultry veterinarian assisting a farmer in Pakistan.",
        "",
        "RULES:",
        "- Reply in the same language the farmer uses (Urdu or English). Detect per-message.",
        "- Keep answers under 120 words unless the farmer asks for more detail.",
        "- Use simple, plain language. No jargon unless explaining it.",
        "- Never prescribe human medicine. Only poultry-safe drugs, and always suggest consulting a qualified local vet before administering.",
        "- If the farmer asks about disease symptoms, be concrete: list 3-5 signs, cause, and 2-3 practical actions.",
        "- If asked about unrelated topics (politics, entertainment), politely redirect to poultry care.",
        "- If the farmer writes Urdu, reply in Urdu script. If English, reply in English.",
        "- Format answers in short paragraphs or bullet lists — never walls of text.",
    ]
    if farm_name:
        context_lines.append(f"\nFARMER CONTEXT:\n- Farm name: {farm_name}")
    if last_diagnosis:
        disease = last_diagnosis.get('disease_name') or 'Unknown'
        confidence = last_diagnosis.get('confidence') or 0
        context_lines.append(
            f"- Most recent diagnosis: {disease} (confidence {round(float(confidence), 1)}%)"
        )
        context_lines.append(
            "  If the farmer asks about their latest result, refer to this diagnosis."
        )
    return '\n'.join(context_lines)


def _sanitize_history(raw_history):
    """
    Accept the client-provided history as a list of {role, text} dicts and
    drop anything malformed. Trim to the last MAX_HISTORY_TURNS so we never
    feed the model unbounded context. Gemini expects roles 'user' / 'model'.
    """
    if not isinstance(raw_history, list):
        return []
    cleaned = []
    for entry in raw_history[-MAX_HISTORY_TURNS:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get('role')
        text = entry.get('text')
        if role not in ('user', 'model'):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        cleaned.append({
            'role': role,
            'parts': [text[:MAX_MESSAGE_CHARS]],
        })
    return cleaned


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
        if not _ensure_genai_configured():
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

        history = _sanitize_history(request.data.get('history'))

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

        try:
            # gemini-2.5-flash gives us the best free-tier quota (1500 req/day,
            # 1M tokens/min) with genuinely strong Urdu support. flash-lite is
            # faster but weaker at Urdu; pro is overkill and counted against a
            # much lower RPD cap.
            model = genai.GenerativeModel(
                model_name='gemini-2.5-flash',
                system_instruction=system_prompt,
                generation_config={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_output_tokens': 512,
                },
            )
            chat = model.start_chat(history=history)
            response = chat.send_message(message)
            reply = (getattr(response, 'text', None) or '').strip()
            if not reply:
                return Response(
                    {'error': 'empty_reply'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response({'reply': reply})
        except Exception as e:  # noqa: BLE001
            # Specific retryable patterns bubble up as 429/quota. Map into a
            # 502 so the client retry path kicks in rather than showing a
            # generic server error.
            logger.exception('Gemini call failed')
            return Response(
                {'error': 'upstream_error', 'detail': str(e)[:200]},
                status=status.HTTP_502_BAD_GATEWAY,
            )
