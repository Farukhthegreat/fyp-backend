"""Daily auto-tip article generator.

Runs once per day from the Render cron service. Uses Gemini 2.5 Flash to
write a short, season-aware poultry-care tip and stores it as an
``Article`` row tagged ``is_auto_generated=True`` so the mobile client
can pin it at the top of the Education tab as "Today's Tip" without
confusing it with curated content.

Free-tier safe: 1 Gemini call per day, regardless of user count.

Run:
    python manage.py generate_daily_tip
    python manage.py generate_daily_tip --dry-run
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Article


logger = logging.getLogger(__name__)


# Pakistani seasons drive most poultry concerns — picking the right
# season hint matters more than absolute month, so map calendar months
# onto the four-season scheme local farmers actually use.
_SEASON_BY_MONTH = {
    12: 'winter', 1: 'winter', 2: 'winter',
    3: 'spring', 4: 'spring',
    5: 'summer', 6: 'summer', 7: 'summer', 8: 'summer',
    9: 'autumn', 10: 'autumn', 11: 'autumn',
}

_CATEGORY_BY_SEASON = {
    'winter': 'seasonal',
    'spring': 'health',
    'summer': 'seasonal',
    'autumn': 'management',
}


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


def _strip_markdown(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^\s{0,3}#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text


def _build_prompt(today: dt.date, season: str, category: str) -> str:
    return (
        f"Today is {today.isoformat()} ({season} season in Pakistan, "
        f"category '{category}').\n"
        "Write a single 'Tip of the Day' for a Pakistani poultry farmer. "
        "Pick a topic that matters for THIS specific season and category. "
        "Output STRICT JSON, nothing else.\n\n"
        "Schema:\n"
        "{\n"
        '  "title": "<English title, max 60 chars, plain text>",\n'
        '  "title_ur": "<Urdu translation of the title, in Pakistani Urdu>",\n'
        '  "content": "<English body, 80-140 words, 1 short intro line, '
        '3-5 actionable bullets prefixed with - , 1 closing line>",\n'
        '  "content_ur": "<full Pakistani-Urdu version of the body, '
        'same structure, written for a barely-literate farmer — short '
        'words, simple grammar, common village vocabulary>"\n'
        "}\n\n"
        "RULES:\n"
        "- No markdown asterisks, underscores, or headings.\n"
        "- Bullets prefixed with '- '.\n"
        "- Don't recommend human-only drugs. Poultry-safe brands or "
        "general advice (vitamins, electrolytes, ventilation) only.\n"
        "- Mention concrete numbers where useful (e.g., 'litter depth "
        "5–7 cm', 'water 4× per day').\n"
        "- Avoid generic platitudes ('always be careful').\n"
        "- Return ONLY the JSON object."
    )


def call_gemini(today: dt.date, season: str, category: str) -> dict | None:
    client, types, err = _ensure_client()
    if client is None:
        logger.warning('Gemini unavailable for daily tip: %s', err)
        return None
    prompt = _build_prompt(today, season, category)
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Content(
                    role='user',
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.55,
                max_output_tokens=900,
                response_mime_type='application/json',
            ),
        )
        raw = (getattr(response, 'text', None) or '').strip()
        if not raw:
            return None
        if raw.startswith('```'):
            raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
            raw = re.sub(r'\n?```\s*$', '', raw)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        return {
            'title': _strip_markdown(str(parsed.get('title') or '')).strip(),
            'title_ur': _strip_markdown(str(parsed.get('title_ur') or '')).strip(),
            'content': _strip_markdown(str(parsed.get('content') or '')).strip(),
            'content_ur': _strip_markdown(str(parsed.get('content_ur') or '')).strip(),
        }
    except Exception:
        logger.exception('Gemini daily tip call failed')
        return None


class Command(BaseCommand):
    help = 'Generate one auto-tip article via Gemini and persist as Article.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Print payload without writing.')
        parser.add_argument('--force', action='store_true',
                            help='Generate even if today already has an auto tip.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        today = (timezone.now() + dt.timedelta(hours=5)).date()
        season = _SEASON_BY_MONTH.get(today.month, 'health')
        category = _CATEGORY_BY_SEASON.get(season, 'health')

        # Idempotency — one auto tip per calendar day. Re-running the
        # cron during the day shouldn't spam Articles.
        if not force:
            already = Article.objects.filter(
                is_auto_generated=True,
                created_at__date=today,
            ).first()
            if already is not None:
                self.stdout.write(
                    f'Auto tip already exists for {today}: id={already.id}, skipping.'
                )
                return

        self.stdout.write(self.style.NOTICE(
            f'Generating daily tip — date={today} season={season} category={category} dry_run={dry_run}'
        ))

        payload = call_gemini(today, season, category)
        if not payload or not payload.get('title') or not payload.get('content'):
            self.stdout.write(self.style.WARNING(
                'Gemini returned empty payload — skipping write.'
            ))
            return

        if dry_run:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        Article.objects.create(
            title=payload['title'][:255],
            title_ur=payload['title_ur'][:255],
            content=payload['content'],
            content_ur=payload['content_ur'],
            category=category,
            is_published=True,
            is_auto_generated=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'  [TIP] {payload["title"][:80]}'
        ))
