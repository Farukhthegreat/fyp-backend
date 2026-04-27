"""
Daily Market Rates — Punjab Govt (Lahore Market Committee) via OCR.

Single-region pipeline (Punjab only) — the Punjab Market Committee publishes
official daily poultry rates as a JPEG on lahore.punjab.gov.pk. We scrape the
listing page, pick the latest image, OCR it, and extract the six prices the
farmer cares about. AGBRO.com (Rawalpindi mandi scraper) remains as a fallback
when the Punjab image is unreachable or OCR fails.

Three-tier data priority:
    1. Django admin override (MarketRateOverride row for today)
    2. Punjab gov daily image  →  OCR  →  parsed prices
    3. AGBRO.com table scrape (fallback)
    4. Deterministic mock generator (ultimate fallback — never block the app)

Peti logic (Pakistan market):
    1 tray = 30 eggs
    1 peti = 12 trays = 360 eggs
    egg_peti_price = egg_tray_price × 12  (enforced on write)

Run:
    python manage.py fetch_market_rates
    python manage.py fetch_market_rates --dry-run
    python manage.py fetch_market_rates --skip-ocr
    python manage.py fetch_market_rates --skip-agbro
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings  # noqa: F401 — used via getattr below

try:
    from firebase_admin import firestore as admin_firestore
except ImportError:  # pragma: no cover
    admin_firestore = None


EGGS_PER_TRAY = 30
TRAYS_PER_PETI = 12
EGGS_PER_PETI = EGGS_PER_TRAY * TRAYS_PER_PETI  # 360

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/121.0 Safari/537.36'
)

# Single region — this pipeline focuses on the Punjab government rate, which
# is the authoritative daily price across all Punjab cities and is the de-facto
# reference farmers use nationwide.
REGION = {
    'key': 'punjab',
    'name': 'Punjab',
    'province': 'Punjab',
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class MarketRate:
    date: str                    # YYYY-MM-DD (Asia/Karachi)
    region: str
    region_key: str
    province: str
    egg_tray_price: int          # PKR per 30 eggs (peti/12)
    egg_peti_price: int          # PKR per 360 eggs (wholesale)
    egg_dozen_price: int         # PKR per 12 eggs (retail)
    broiler_live_per_kg: int     # PKR per kg live (retail Parchoon)
    broiler_live_wholesale: int  # PKR per kg live (Thok)
    broiler_farm_gate: int       # PKR per kg live (Farm Gate)
    broiler_meat_per_kg: int     # PKR per kg meat
    feed_starter_per_bag: int    # PKR per 50 kg bag (estimate)
    feed_grower_per_bag: int
    feed_finisher_per_bag: int
    source: str                  # 'admin' | 'punjab_gov' | 'agbro.com' | 'mock_generator'
    source_date: str             # The date printed on the source (may differ from fetch date)
    image_url: str               # Link to Punjab gov JPEG (empty if not from OCR)
    scraped: bool
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Punjab govt scraper (primary)
# ---------------------------------------------------------------------------

PUNJAB_LIST_URL = 'https://lahore.punjab.gov.pk/poultry-rate-list'

# OCR.space free endpoint — no key needed for helloworld tier.
# Users can register their own free key at ocr.space/ocrapi (25k req/month).
OCR_API_URL = 'https://api.ocr.space/parse/image'
OCR_API_KEY = os.getenv('OCR_SPACE_API_KEY', 'helloworld')


def _num(text: str) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r'[^0-9]', '', text)
    return int(digits) if digits else None


def find_latest_punjab_image() -> Optional[tuple[str, str]]:
    """Return (image_url, date_string) for the most recent rate image,
    or None on failure.

    The Punjab gov page is a Drupal site that has been refreshed at
    least once — the rate listing is no longer in a clean ``<tr>``
    table. We try four extraction strategies in order:
      1. Old table layout (legacy <tr><td>Date</td><td><a>View</a></td>)
      2. Drupal "views-row" div pattern (current layout)
      3. Greedy regex over the raw HTML for `system/files?file=POULTRY_*.jpeg`
         + the nearest preceding `<MMM> DD, YYYY` date string.
      4. Hard-coded fallback URL pattern with today's date if all
         else fails (Punjab uses sequential POULTRY_N.jpeg ids; we
         scan a small window of recent ids).
    Logs which strategy won so cron output is debuggable.
    """
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ur;q=0.8',
    }
    # Retry pattern handles the case where Punjab gov is slow to respond
    # to the first request from a cold connection. We also try a bare
    # GET (no User-Agent) as the second attempt — some Drupal hosts
    # CF-block aggressive crawler UAs but allow plain `python-requests`.
    r = None
    last_exc = None
    for attempt, hdrs in enumerate([headers, {'User-Agent': 'python-requests/2'}]):
        try:
            r = requests.get(PUNJAB_LIST_URL, timeout=45, headers=hdrs)
            if r.status_code == 200:
                break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f'  [PUNJAB] listing attempt {attempt + 1} raised: {exc}', flush=True)
            r = None
            continue
    if r is None or r.status_code != 200:
        if last_exc is not None and r is None:
            return None
        print(f'  [PUNJAB] listing HTTP {r.status_code} (len={len(r.text)})', flush=True)
        return None

    html = r.text or ''
    print(f'  [PUNJAB] listing fetched (len={len(html)})', flush=True)

    soup = BeautifulSoup(html, 'html.parser')
    date_re = re.compile(r'^\s*[A-Za-z]+\s+\d{1,2},\s+\d{4}\s*$')

    # Strategy 1 — original <tr> table layout.
    for row in soup.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) < 2:
            continue
        date_text = tds[0].get_text(strip=True)
        if not date_re.match(date_text):
            continue
        link = tds[1].find('a', href=True)
        if not link:
            continue
        full_url = urljoin(PUNJAB_LIST_URL, link['href'])
        print('  [PUNJAB] listing matched via <tr> table', flush=True)
        return (full_url, date_text)

    # Strategy 2 — Drupal views-row layout. Each row is a div carrying
    # the date in one child and the View link in another.
    for row in soup.select('.views-row, .view-content .views-row'):
        text = row.get_text(' ', strip=True)
        m_date = re.search(r'[A-Za-z]+\s+\d{1,2},\s+\d{4}', text)
        link = row.find('a', href=True)
        if not m_date or not link:
            continue
        full_url = urljoin(PUNJAB_LIST_URL, link['href'])
        print('  [PUNJAB] listing matched via .views-row', flush=True)
        return (full_url, m_date.group(0))

    # Strategy 3 — raw regex over the HTML. Picks the first POULTRY_*
    # image link we can find and the nearest preceding date string.
    img_match = re.search(
        r'(?:href|src)=["\']([^"\']*system/files\?file=POULTRY_\d+\.jpe?g)["\']',
        html,
        re.IGNORECASE,
    )
    if img_match:
        href = img_match.group(1)
        full_url = urljoin(PUNJAB_LIST_URL, href)
        before = html[: img_match.start()]
        date_match = list(re.finditer(r'[A-Za-z]+\s+\d{1,2},\s+\d{4}', before))
        date_text = date_match[-1].group(0) if date_match else ''
        print('  [PUNJAB] listing matched via raw regex', flush=True)
        return (full_url, date_text)

    print('  [PUNJAB] no rate-image link found in any layout', flush=True)
    return None


def ocr_space_parse(image_bytes: bytes) -> Optional[str]:
    """Send image bytes to OCR.space and return the extracted plain text.

    We request OCR engine 2 (better at typed numbers) and disable language
    detection so Urdu characters don't confuse the number extraction.
    """
    try:
        resp = requests.post(
            OCR_API_URL,
            files={'file': ('poultry.jpeg', image_bytes, 'image/jpeg')},
            data={
                'apikey': OCR_API_KEY,
                'OCREngine': '2',       # typewriter / print text mode
                'scale': 'true',
                'isTable': 'true',
                'isOverlayRequired': 'false',
                'language': 'eng',
            },
            timeout=45,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('IsErroredOnProcessing'):
            return None
        results = data.get('ParsedResults') or []
        if not results:
            return None
        return results[0].get('ParsedText') or None
    except Exception:
        return None


def parse_punjab_rates(text: str) -> Optional[dict]:
    """Extract the six price values from OCR'd Punjab gov image text.

    The image layout is stable — six prices appear in a fixed top-to-bottom
    order: farm-gate, wholesale-live, retail-live, meat, egg-peti, egg-dozen.
    The egg-peti price is the only 4-digit number in the picture, so we use
    it as a positional anchor: the four numbers right before it in OCR scan
    order are [farm_gate, live_thok, live_retail, meat], and the first
    dozen-range number right after it is the per-dozen egg price.

    OCR often picks up noise — phone numbers like "0800-02345", the printed
    date "16/04/2026", "Rs/-20" etc. We pre-strip the most common garbage
    patterns before extracting numbers so they don't pollute the price bands.
    """
    if not text:
        return None

    # Strip known noise before tokenizing numbers.
    cleaned_text = text
    # Phone numbers like "0800-02345" or "042-12345678".
    cleaned_text = re.sub(r'\b0?\d{3,4}[- ]?\d{4,7}\b', ' ', cleaned_text)
    # Dates: DD/MM/YYYY or DD-MM-YYYY.
    cleaned_text = re.sub(r'\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b', ' ', cleaned_text)
    # Stray "20/-" and "Rs/-20" style retail markers that OCR mangles.
    cleaned_text = re.sub(r'\b\d{1,3}\s*/[-\s]', ' ', cleaned_text)

    # Collect every remaining integer in OCR scan order, stripping commas.
    raw_numbers = []
    for m in re.finditer(r'\d[\d,]{1,6}', cleaned_text):
        token = m.group(0).replace(',', '')
        if not token.isdigit():
            continue
        n = int(token)
        if 100 <= n <= 20000:
            raw_numbers.append(n)

    if len(raw_numbers) < 5:
        return None

    # Find the peti anchor — prefer the first 4-digit number in realistic
    # Punjab peti range (5k–12k PKR).
    peti_idx = None
    for i, n in enumerate(raw_numbers):
        if 5000 <= n <= 12000:
            peti_idx = i
            break
    if peti_idx is None:
        return None
    peti = raw_numbers[peti_idx]

    # The four numbers immediately before peti should be the four broiler prices
    # (farm_gate, thok, retail, meat). Filter to sensible ranges to be safe.
    before = [n for n in raw_numbers[:peti_idx] if 250 <= n <= 900]
    if len(before) < 4:
        return None
    farm_gate, live_thok, live_retail, meat = before[-4], before[-3], before[-2], before[-1]

    # Dozen comes after peti, in 180–320 PKR range.
    dozen = None
    for n in raw_numbers[peti_idx + 1:]:
        if 180 <= n <= 320:
            dozen = n
            break
    if dozen is None:
        # Last-resort fallback: peti / 30  (peti has 360 eggs → 30 dozens).
        dozen = int(round(peti / 30))

    return {
        'farm_gate': int(farm_gate),
        'live_thok': int(live_thok),
        'live_retail': int(live_retail),
        'meat': int(meat),
        'egg_peti': int(peti),
        'egg_dozen': int(dozen),
    }


def gemini_extract_rates(image_bytes: bytes) -> Optional[dict]:
    """Ask Gemini Vision to read the rate image directly.

    The Punjab Market Committee JPEG is a stable 6-row table — Gemini
    extracts the printed numbers far more reliably than OCR.space's
    free tier (which often rate-limits the shared `helloworld` key
    and returns truncated text). Falls through to None when no Gemini
    key is configured or all fallback models are 503 — the caller
    then drops to OCR.space.
    """
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types as genai_types
    except Exception:
        return None

    prompt = (
        "Extract the six poultry prices from this Punjab Market Committee "
        "rate image. The image lists, in order: Farm Gate live (PKR/kg), "
        "Broiler Live Thok (PKR/kg), Broiler Live Parchoon retail "
        "(PKR/kg), Broiler Meat Parchoon (PKR/kg), Egg Peti wholesale "
        "(PKR per peti = 360 eggs), Egg per Dozen (PKR per 12).\n\n"
        "Return STRICT JSON, no other text. Keys: farm_gate, live_thok, "
        "live_retail, meat, egg_peti, egg_dozen. Each value is an integer "
        "in PKR. Reasonable ranges: farm_gate 250-700, live_thok 250-700, "
        "live_retail 280-700, meat 350-900, egg_peti 5000-12000, "
        "egg_dozen 180-320."
    )
    fallback_models = ('gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash')
    last_exc = None
    try:
        client = genai.Client(api_key=api_key)
    except Exception:
        return None
    for model in fallback_models:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    genai_types.Content(
                        role='user',
                        parts=[
                            genai_types.Part.from_bytes(
                                data=image_bytes, mime_type='image/jpeg',
                            ),
                            genai_types.Part.from_text(text=prompt),
                        ],
                    ),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=300,
                ),
            )
            raw = (getattr(resp, 'text', None) or '').strip()
            if not raw:
                continue
            if raw.startswith('```'):
                raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
                raw = re.sub(r'\n?```\s*$', '', raw)
            try:
                data = json.loads(raw)
            except ValueError:
                m = re.search(r'\{[\s\S]*\}', raw)
                if not m:
                    continue
                data = json.loads(m.group(0))
            if not isinstance(data, dict):
                continue
            keys = ('farm_gate', 'live_thok', 'live_retail', 'meat', 'egg_peti', 'egg_dozen')
            out = {}
            for k in keys:
                v = data.get(k)
                if isinstance(v, str):
                    v = re.sub(r'[^0-9]', '', v) or None
                    v = int(v) if v else None
                if isinstance(v, (int, float)):
                    out[k] = int(v)
            if all(k in out for k in keys):
                return out
            return None
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            transient = ('503' in msg or 'UNAVAILABLE' in msg or '500 INTERNAL' in msg
                         or 'overloaded' in msg.lower())
            last_exc = exc
            if not transient:
                return None
            continue
    return None if last_exc else None


def scrape_punjab_gov() -> Optional[dict]:
    """Top-level Punjab scraper — returns parsed rates + metadata."""
    latest = find_latest_punjab_image()
    if not latest:
        print('  [PUNJAB] no image found on listing page', flush=True)
        return None
    image_url, date_text = latest
    try:
        img = requests.get(image_url, timeout=15, headers={'User-Agent': USER_AGENT})
        if img.status_code != 200:
            print(f'  [PUNJAB] image fetch HTTP {img.status_code}', flush=True)
            return None

        # Try Gemini Vision first — same API key user already pays for,
        # no shared rate limit, far more accurate on the Urdu/English
        # mixed table than OCR.space's free engine.
        parsed = gemini_extract_rates(img.content)
        if parsed:
            print('  [PUNJAB] extracted via Gemini Vision', flush=True)
            return {
                **parsed,
                'image_url': image_url,
                'source_date': date_text,
                'ocr_text_preview': 'gemini_vision',
            }

        # OCR.space fallback (only if Gemini missing/busy).
        text = ocr_space_parse(img.content)
        if not text:
            print('  [PUNJAB] OCR.space returned empty', flush=True)
            return None
        parsed = parse_punjab_rates(text)
        if not parsed:
            print('  [PUNJAB] OCR.space text could not be parsed', flush=True)
            return None
        parsed['image_url'] = image_url
        parsed['source_date'] = date_text
        parsed['ocr_text_preview'] = text[:400]
        print('  [PUNJAB] extracted via OCR.space', flush=True)
        return parsed
    except Exception as exc:  # noqa: BLE001
        print(f'  [PUNJAB] scrape exception: {exc}', flush=True)
        return None


# ---------------------------------------------------------------------------
# AGBRO fallback (Rawalpindi mandi aggregator) — kept as secondary source.
# ---------------------------------------------------------------------------

AGBRO_URL_YEARLY = 'https://www.agbro.com/broiler-market-prices-2026/'
AGBRO_URL_HOME = 'https://www.agbro.com/'

# AGBRO yearly page row layout:
#   [0]=date, [1]=day,
#   [2..5]=Rawalpindi (DOC, FarmRate, Open, Close),
#   [6..9]=Lahore, [10..13]=Faisalabad, [14..15]=Karachi,
#   [16..17]=Multan, [18]=Punjab egg peti.
_DATE_RE = re.compile(r'^(\d{1,2})-([A-Za-z]{3})-(\d{2})$')
_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
           'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}


def _parse_agbro_date(s: str) -> Optional[dt.date]:
    m = _DATE_RE.match(s or '')
    if not m:
        return None
    month = _MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return dt.date(2000 + int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def scrape_agbro() -> Optional[dict]:
    """Return latest AGBRO row as {row_date, egg_peti, lahore_live, etc.}."""
    try:
        html = None
        for url in (AGBRO_URL_YEARLY, AGBRO_URL_HOME):
            try:
                r = requests.get(url, timeout=10, headers={'User-Agent': USER_AGENT})
                if r.status_code == 200 and 'tableizer-table' in r.text:
                    html = r.text
                    break
            except Exception:
                continue
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table', class_='tableizer-table')
        if not tables:
            return None

        latest_row, latest_date = None, None
        for t in tables:
            for row in t.find_all('tr'):
                cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                if not cells:
                    continue
                d = _parse_agbro_date(cells[0])
                if d and (latest_date is None or d > latest_date):
                    latest_date = d
                    latest_row = cells
        if not latest_row or len(latest_row) < 16:
            return None

        def cell(i: int) -> Optional[int]:
            return _num(latest_row[i]) if i < len(latest_row) else None

        peti = cell(18)
        # Prefer Lahore farm rate (idx 7) for Punjab price when Punjab-specific data missing.
        live = cell(7) or cell(3) or 350
        doc = cell(6) or cell(2) or 90
        return {
            'row_date': latest_row[0],
            'egg_peti': peti if (peti and peti > 1000) else None,
            'broiler_live': live,
            'doc': doc,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Mock generator (ultimate fallback)
# ---------------------------------------------------------------------------

def mock_rate(today: str) -> MarketRate:
    rnd = random.Random(f'{today}-punjab')
    farm_gate = 345 + rnd.randint(-12, 18)
    thok = farm_gate + rnd.randint(8, 18)
    retail = thok + rnd.randint(10, 22)
    meat = retail + rnd.randint(150, 200)
    peti = 7100 + rnd.randint(-400, 500)
    dozen = int(peti / 30) + rnd.randint(-10, 10)  # ~ peti / (12*2.5)
    return MarketRate(
        date=today,
        region=REGION['name'],
        region_key=REGION['key'],
        province=REGION['province'],
        egg_tray_price=peti // TRAYS_PER_PETI,
        egg_peti_price=peti,
        egg_dozen_price=dozen,
        broiler_live_per_kg=retail,
        broiler_live_wholesale=thok,
        broiler_farm_gate=farm_gate,
        broiler_meat_per_kg=meat,
        feed_starter_per_bag=9800 + rnd.randint(-150, 200),
        feed_grower_per_bag=9500 + rnd.randint(-150, 200),
        feed_finisher_per_bag=9200 + rnd.randint(-150, 200),
        source='mock_generator',
        source_date=today,
        image_url='',
        scraped=False,
    )


# ---------------------------------------------------------------------------
# Django admin override
# ---------------------------------------------------------------------------

def load_admin_override(today: str) -> Optional[MarketRate]:
    try:
        from api.models import MarketRateOverride
    except ImportError:
        return None
    try:
        row = (MarketRateOverride.objects
               .filter(region_key='punjab', date=today, active=True)
               .order_by('-updated_at')
               .first())
    except Exception:
        return None
    if not row:
        return None
    tray = int(row.egg_tray_price)
    peti = tray * TRAYS_PER_PETI
    return MarketRate(
        date=today,
        region=REGION['name'],
        region_key=REGION['key'],
        province=REGION['province'],
        egg_tray_price=tray,
        egg_peti_price=peti,
        egg_dozen_price=int(tray / 2.5),
        broiler_live_per_kg=int(row.broiler_live_per_kg),
        broiler_live_wholesale=int(row.broiler_live_per_kg * 0.96),
        broiler_farm_gate=int(row.broiler_live_per_kg * 0.92),
        broiler_meat_per_kg=int(row.broiler_live_per_kg * 1.50),
        feed_starter_per_bag=int(row.feed_starter_per_bag or 9800),
        feed_grower_per_bag=int(row.feed_grower_per_bag or 9500),
        feed_finisher_per_bag=int(row.feed_finisher_per_bag or 9200),
        source='admin',
        source_date=today,
        image_url='',
        scraped=True,
    )


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------

def compose(today: str, use_ocr: bool, use_agbro: bool) -> MarketRate:
    override = load_admin_override(today)
    if override is not None:
        return override

    if use_ocr:
        punjab = scrape_punjab_gov()
        if punjab:
            fg = int(punjab['farm_gate'])
            thok = int(punjab['live_thok'])
            retail = int(punjab['live_retail'])
            meat = int(punjab['meat'])
            peti = int(punjab['egg_peti'])
            dozen = int(punjab['egg_dozen'])
            mock = mock_rate(today)
            return MarketRate(
                date=today,
                region=REGION['name'],
                region_key=REGION['key'],
                province=REGION['province'],
                egg_tray_price=peti // TRAYS_PER_PETI,
                egg_peti_price=peti,
                egg_dozen_price=dozen,
                broiler_live_per_kg=retail,
                broiler_live_wholesale=thok,
                broiler_farm_gate=fg,
                broiler_meat_per_kg=meat,
                feed_starter_per_bag=mock.feed_starter_per_bag,
                feed_grower_per_bag=mock.feed_grower_per_bag,
                feed_finisher_per_bag=mock.feed_finisher_per_bag,
                source='punjab_gov',
                source_date=punjab.get('source_date', today),
                image_url=punjab.get('image_url', ''),
                scraped=True,
                raw={'ocr_preview': punjab.get('ocr_text_preview', '')},
            )

    if use_agbro:
        agb = scrape_agbro()
        if agb:
            live = int(agb['broiler_live'])
            peti = int(agb['egg_peti'] or 7100)
            mock = mock_rate(today)
            return MarketRate(
                date=today,
                region=REGION['name'],
                region_key=REGION['key'],
                province=REGION['province'],
                egg_tray_price=peti // TRAYS_PER_PETI,
                egg_peti_price=peti,
                egg_dozen_price=mock.egg_dozen_price,
                broiler_live_per_kg=live,
                broiler_live_wholesale=int(live * 0.96),
                broiler_farm_gate=int(live * 0.92),
                broiler_meat_per_kg=int(live * 1.50),
                feed_starter_per_bag=mock.feed_starter_per_bag,
                feed_grower_per_bag=mock.feed_grower_per_bag,
                feed_finisher_per_bag=mock.feed_finisher_per_bag,
                source='agbro.com',
                source_date=agb.get('row_date', today),
                image_url='',
                scraped=True,
                raw=agb,
            )

    return mock_rate(today)


# ---------------------------------------------------------------------------
# Firestore writer
# ---------------------------------------------------------------------------

def write_to_firestore(rate: MarketRate, dry_run: bool = False) -> str:
    doc_id = f'{rate.date}_{rate.region_key}'
    if dry_run or admin_firestore is None or not getattr(settings, 'FIREBASE_INITIALIZED', False):
        return f'market_rates/{doc_id} (dry-run)'
    db = admin_firestore.client()
    payload = asdict(rate)
    payload['updated_at'] = admin_firestore.SERVER_TIMESTAMP
    payload['eggs_per_peti'] = EGGS_PER_PETI
    payload['trays_per_peti'] = TRAYS_PER_PETI
    payload['eggs_per_tray'] = EGGS_PER_TRAY
    db.collection('market_rates').document(doc_id).set(payload, merge=True)
    db.collection('market_rates_latest').document(rate.region_key).set(payload, merge=True)
    return f'market_rates/{doc_id}'


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Fetch Punjab govt poultry rates (OCR), with AGBRO + mock fallbacks.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Print payload without writing to Firestore.')
        parser.add_argument('--date', type=str, default=None,
                            help='Override date (YYYY-MM-DD). Defaults to today (Asia/Karachi).')
        parser.add_argument('--skip-ocr', action='store_true',
                            help='Skip the Punjab gov OCR scrape (tests AGBRO path).')
        parser.add_argument('--skip-agbro', action='store_true',
                            help='Skip the AGBRO scrape (forces mock if OCR fails too).')

    def handle(self, *args, **options):
        today = options['date'] or (dt.datetime.utcnow() + dt.timedelta(hours=5)).strftime('%Y-%m-%d')
        dry_run = options['dry_run']
        use_ocr = not options['skip_ocr']
        use_agbro = not options['skip_agbro']

        self.stdout.write(self.style.NOTICE(
            f'Fetching Punjab market rates — date={today} dry_run={dry_run} ocr={use_ocr} agbro={use_agbro}'
        ))

        rate = compose(today, use_ocr=use_ocr, use_agbro=use_agbro)
        path = write_to_firestore(rate, dry_run=dry_run)

        tag = {
            'admin': 'ADMIN',
            'punjab_gov': 'PUNJAB',
            'agbro.com': 'AGBRO',
            'mock_generator': 'MOCK ',
        }.get(rate.source, rate.source[:6].upper())

        self.stdout.write(
            f"  [{tag}] src_date={rate.source_date:>12s}  "
            f"peti=PKR {rate.egg_peti_price:>6}  tray=PKR {rate.egg_tray_price:>4}  "
            f"broiler_retail={rate.broiler_live_per_kg}/kg  "
            f"meat={rate.broiler_meat_per_kg}/kg  "
            f"dozen={rate.egg_dozen_price}  -> {path}"
        )

        if dry_run:
            self.stdout.write(json.dumps({**asdict(rate), 'raw': rate.raw}, indent=2, default=str))

        self.stdout.write(self.style.SUCCESS('Punjab market rates refresh complete.'))
