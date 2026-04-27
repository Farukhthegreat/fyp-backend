"""Daily morning brief — single FCM topic broadcast.

Calls Gemini once for a generic Pakistani-Urdu morning brief that mixes
the season's top poultry concern with today's market rate (when
available). Pushes the brief to the ``daily_brief`` FCM topic so every
subscribed farmer device receives it from a single fan-out call —
this is what keeps us inside the Gemini free tier (1 RPD/day for the
brief, regardless of user count).

Run:
    python manage.py send_daily_brief
    python manage.py send_daily_brief --dry-run
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.notifications import send_fcm_topic


logger = logging.getLogger(__name__)


# Top Punjab/Sindh seasonal concerns mapped to a 1-line hint Gemini can
# anchor the brief to. Helps the model write something concrete instead
# of generic "take care of your flock" filler.
_SEASON_HINTS = {
    'winter': 'Cold stress, ventilation vs draft trade-off, brooder temp.',
    'spring': 'Vaccination boosters, mite/lice surge, rising humidity.',
    'summer': 'Heat stress, electrolytes, cool clean water, mortality risk.',
    'autumn': 'Litter management, ammonia build-up, NCD/IBD risk.',
}

_SEASON_BY_MONTH = {
    12: 'winter', 1: 'winter', 2: 'winter',
    3: 'spring', 4: 'spring',
    5: 'summer', 6: 'summer', 7: 'summer', 8: 'summer',
    9: 'autumn', 10: 'autumn', 11: 'autumn',
}


_GEMINI_FALLBACK_MODELS = (
    'gemini-2.0-flash-lite',
    'gemini-3.1-flash-lite-preview',
    'gemini-3-flash-preview',
    'gemini-2.0-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash',
    'gemini-2.5-pro',
)


def _ensure_client():
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None, None, 'GEMINI_API_KEY missing'
    try:
        from google import genai
        from google.genai import types as genai_types
        return genai.Client(api_key=api_key), genai_types, None
    except Exception as exc:  # noqa: BLE001
        return None, None, f'genai init failed: {exc}'


def _gen_with_fallback(client, contents, config):
    last_exc = None
    for model in _GEMINI_FALLBACK_MODELS:
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            transient = (
                ' 503 ' in f' {msg} '
                or 'UNAVAILABLE' in msg
                or '500 INTERNAL' in msg
                or 'overloaded' in msg.lower()
                or ' 429 ' in f' {msg} '
                or 'RESOURCE_EXHAUSTED' in msg
                or 'quota' in msg.lower()
                or ' 404 ' in f' {msg} '
                or 'NOT_FOUND' in msg
                or 'is not found' in msg.lower()
                or 'INVALID_ARGUMENT' in msg
            )
            last_exc = exc
            if not transient:
                raise
            logger.warning('Gemini %s busy, trying next model', model)
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('No Gemini fallback succeeded')


def _strip_markdown(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text, flags=re.DOTALL)
    return text


def _latest_market_summary() -> str:
    """Best-effort Punjab market rate snapshot. Returns a 1-line summary
    or an empty string when Firestore isn't reachable."""
    try:
        from firebase_admin import firestore as admin_firestore
        from django.conf import settings
        if not getattr(settings, 'FIREBASE_INITIALIZED', False):
            return ''
        db = admin_firestore.client()
        doc = db.collection('market_rates_latest').document('punjab').get()
        if not doc.exists:
            return ''
        d = doc.to_dict() or {}
        peti = d.get('egg_peti_price')
        live = d.get('broiler_live_per_kg')
        bits = []
        if peti:
            bits.append(f'egg peti PKR {int(peti)}')
        if live:
            bits.append(f'broiler retail PKR {int(live)}/kg')
        return ', '.join(bits)
    except Exception:
        return ''


def _build_prompt(today: dt.date, season: str, hint: str, market: str) -> str:
    market_line = market or 'no fresh market rate available'
    return (
        f"Date: {today.isoformat()} ({season} season in Pakistan).\n"
        f"Seasonal focus: {hint}\n"
        f"Today's market: {market_line}.\n"
        "Write a SHORT morning brief for a Pakistani poultry farmer. "
        "Output STRICT JSON only.\n\n"
        "Schema:\n"
        "{\n"
        '  "title_en": "<English notification title, max 50 chars>",\n'
        '  "body_en": "<English body, 80-130 chars, 1 sentence with one '
        'concrete action>",\n'
        '  "title_ur": "<Pakistani-Urdu title>",\n'
        '  "body_ur": "<Pakistani-Urdu body matching the English meaning>"\n'
        "}\n\n"
        "RULES:\n"
        "- Plain text inside the JSON strings (no markdown).\n"
        "- Tie the body to the seasonal focus and, when available, the "
        "market line ('peti rate badh gaya hai' / 'broiler price strong "
        "hai aaj').\n"
        "- One concrete action per language.\n"
        "- Pakistani-Urdu: short words, simple grammar, common village "
        "vocabulary.\n"
        "- Return ONLY the JSON object."
    )


def call_gemini(today: dt.date, season: str, market: str) -> dict | None:
    client, types, err = _ensure_client()
    if client is None:
        logger.warning('Gemini unavailable for daily brief: %s', err)
        return None
    hint = _SEASON_HINTS.get(season, '')
    try:
        response = _gen_with_fallback(
            client,
            contents=[
                types.Content(
                    role='user',
                    parts=[types.Part.from_text(text=_build_prompt(today, season, hint, market))],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=600,
            ),
        )
        raw = (getattr(response, 'text', None) or '').strip()
        # Walk candidates if .text is empty — same SDK quirk as XAI.
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
            logger.warning(
                'Daily brief Gemini empty response (feedback=%r)',
                getattr(response, 'prompt_feedback', None),
            )
            return None
        # Surface a preview so we can see why parse fails.
        preview = raw[:300].replace('\n', ' ')
        logger.info('Daily brief raw preview: %s', preview)
        if raw.startswith('```'):
            raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
            raw = re.sub(r'\n?```\s*$', '', raw)
        try:
            parsed = json.loads(raw)
        except ValueError:
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                logger.warning('Daily brief JSON not found in body: %s', preview)
                return None
            try:
                parsed = json.loads(m.group(0))
            except ValueError as exc:
                logger.warning('Daily brief JSON parse failed: %s | body=%s', exc, preview)
                return None
        if not isinstance(parsed, dict):
            return None
        return {
            'title_en': _strip_markdown(str(parsed.get('title_en') or '')).strip(),
            'body_en': _strip_markdown(str(parsed.get('body_en') or '')).strip(),
            'title_ur': _strip_markdown(str(parsed.get('title_ur') or '')).strip(),
            'body_ur': _strip_markdown(str(parsed.get('body_ur') or '')).strip(),
        }
    except Exception:
        logger.exception('Gemini daily brief call failed')
        return None


class Command(BaseCommand):
    help = 'Compose a Gemini-backed daily brief and broadcast via FCM topic.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Print payload without firing FCM.')
        parser.add_argument('--topic', default='daily_brief',
                            help='FCM topic name (default daily_brief).')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        topic = options['topic']

        today = (timezone.now() + dt.timedelta(hours=5)).date()
        season = _SEASON_BY_MONTH.get(today.month, 'spring')
        market = _latest_market_summary()

        self.stdout.write(self.style.NOTICE(
            f'Composing daily brief — date={today} season={season} dry_run={dry_run}'
        ))

        payload = call_gemini(today, season, market)
        if not payload or not payload.get('title_en') or not payload.get('body_en'):
            self.stdout.write(self.style.WARNING(
                'Gemini returned empty brief — skipping push.'
            ))
            return

        if dry_run:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        # Push the English-side as the primary FCM payload — clients
        # decide which language to render based on their LanguageProvider
        # state, picking the matching key from the data block.
        send_fcm_topic(
            topic=topic,
            title=payload['title_en'],
            body=payload['body_en'],
            data={
                'kind': 'daily_brief',
                'title_en': payload['title_en'],
                'body_en': payload['body_en'],
                'title_ur': payload.get('title_ur', ''),
                'body_ur': payload.get('body_ur', ''),
                'date': today.isoformat(),
                'season': season,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'  [BRIEF] {payload["title_en"][:50]} -> topic={topic}'
        ))
