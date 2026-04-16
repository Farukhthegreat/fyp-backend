"""
Daily Market Rates — fetch + Firestore writer.

Three-tier pipeline (C):
    1. Django admin override (highest priority — if present for today, use it)
    2. AGBRO.com scraper (primary real-data source — 5 PK cities + Punjab egg peti)
    3. Deterministic mock generator (fallback — seeded by date+region)

Writes to Firestore:
    market_rates/{YYYY-MM-DD}_{region_key}
    market_rates_latest/{region_key}      ← pointer to most recent
Triggers Cloud Function (see cloud_functions/) → FCM to topic
    market_rates_{region_key} + market_rates_all.

Peti logic (Pakistan market):
    1 tray     = 30 eggs
    1 peti     = 12 trays = 360 eggs
    peti_price = tray_price * 12

Run:
    python manage.py fetch_market_rates
    python manage.py fetch_market_rates --region lahore
    python manage.py fetch_market_rates --dry-run
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

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

# Regions we track. Keys must be FCM-topic safe ([a-zA-Z0-9-_.~%]).
# `agbro_city` maps to AGBRO column header; None means not on AGBRO → mock only.
# `mirror_of` lets us reuse a sibling region when the source lacks the city
# (Islamabad uses Rawalpindi rates — they share the same mandi).
REGIONS = [
    {'key': 'lahore',     'name': 'Lahore',     'province': 'Punjab',     'agbro_city': 'Lahore',     'mirror_of': None},
    {'key': 'karachi',    'name': 'Karachi',    'province': 'Sindh',      'agbro_city': 'Karachi',    'mirror_of': None},
    {'key': 'rawalpindi', 'name': 'Rawalpindi', 'province': 'Punjab',     'agbro_city': 'Rawalpindi', 'mirror_of': None},
    {'key': 'islamabad',  'name': 'Islamabad',  'province': 'ICT',        'agbro_city': None,         'mirror_of': 'rawalpindi'},
    {'key': 'faisalabad', 'name': 'Faisalabad', 'province': 'Punjab',     'agbro_city': 'Faisalabad', 'mirror_of': None},
    {'key': 'multan',     'name': 'Multan',     'province': 'Punjab',     'agbro_city': 'Multan',     'mirror_of': None},
    {'key': 'peshawar',   'name': 'Peshawar',   'province': 'KPK',        'agbro_city': None,         'mirror_of': 'rawalpindi'},
    {'key': 'quetta',     'name': 'Quetta',     'province': 'Balochistan','agbro_city': None,         'mirror_of': 'karachi'},
]


@dataclass
class MarketRate:
    date: str                    # YYYY-MM-DD
    region: str
    region_key: str
    province: str
    egg_tray_price: int          # PKR per 30 eggs
    egg_peti_price: int          # PKR per 360 eggs (= tray * 12)
    broiler_live_per_kg: int     # PKR per kg live (farm rate)
    broiler_meat_per_kg: int     # PKR per kg meat (est. = live * 1.52)
    doc_price: int               # Day-old chick per chick
    feed_starter_per_bag: int    # PKR per 50 kg
    feed_grower_per_bag: int
    feed_finisher_per_bag: int
    source: str                  # 'admin' | 'agbro.com' | 'mock_generator' | 'mirror:<key>'
    scraped: bool                # True if any real data used
    raw: dict = field(default_factory=dict)  # debug payload from source


# ---------------------------------------------------------------------------
# Mock generator — seeded so same (date, region) always yields same numbers.
# ---------------------------------------------------------------------------

def _baseline(region_key: str) -> dict:
    # April-2026 approximate Pakistan market baselines (PKR).
    return {
        'tray': {'lahore': 335, 'karachi': 345, 'islamabad': 340, 'rawalpindi': 338,
                 'faisalabad': 332, 'multan': 328, 'peshawar': 342, 'quetta': 355}.get(region_key, 340),
        'live': {'lahore': 415, 'karachi': 425, 'islamabad': 420, 'rawalpindi': 418,
                 'faisalabad': 410, 'multan': 405, 'peshawar': 430, 'quetta': 445}.get(region_key, 420),
        'doc':  {'lahore': 70, 'karachi': 72, 'islamabad': 70, 'rawalpindi': 70,
                 'faisalabad': 70, 'multan': 68, 'peshawar': 72, 'quetta': 74}.get(region_key, 70),
    }


def mock_rate(region: dict, today: str) -> MarketRate:
    rnd = random.Random(f'{today}-{region["key"]}')
    b = _baseline(region['key'])
    tray = b['tray'] + rnd.randint(-8, 12)
    live = b['live'] + rnd.randint(-15, 20)
    doc = b['doc'] + rnd.randint(-4, 6)
    return MarketRate(
        date=today,
        region=region['name'],
        region_key=region['key'],
        province=region['province'],
        egg_tray_price=tray,
        egg_peti_price=tray * TRAYS_PER_PETI,
        broiler_live_per_kg=live,
        broiler_meat_per_kg=int(live * 1.52),
        doc_price=doc,
        feed_starter_per_bag=9800 + rnd.randint(-150, 200),
        feed_grower_per_bag=9500 + rnd.randint(-150, 200),
        feed_finisher_per_bag=9200 + rnd.randint(-150, 200),
        source='mock_generator',
        scraped=False,
    )


# ---------------------------------------------------------------------------
# AGBRO.com scraper — parses their daily rates table.
#
# Table layout (19 cells per data row, inferred from live HTML 2026):
#   [0] date (DD-Mon-YY), [1] day
#   [2-5]   Rawalpindi  : DOC, FarmRate, Open, Close
#   [6-9]   Lahore      : DOC, FarmRate, Open, Close
#   [10-13] Faisalabad  : DOC, FarmRate, Open, Close
#   [14-15] Karachi     : DOC, FarmRate
#   [16-17] Multan      : DOC, FarmRate
#   [18]    Punjab Egg Rate (per peti, string may be "10,140")
# ---------------------------------------------------------------------------

AGBRO_URL = 'https://www.agbro.com/'

AGBRO_COL_MAP = {
    'Rawalpindi': {'doc': 2,  'farm': 3,  'open': 4,  'close': 5},
    'Lahore':     {'doc': 6,  'farm': 7,  'open': 8,  'close': 9},
    'Faisalabad': {'doc': 10, 'farm': 11, 'open': 12, 'close': 13},
    'Karachi':    {'doc': 14, 'farm': 15},
    'Multan':     {'doc': 16, 'farm': 17},
}

AGBRO_EGG_PETI_IDX = 18  # Punjab Egg Rate per peti


def _num(cell: str) -> Optional[float]:
    cleaned = re.sub(r'[^0-9.]', '', cell or '')
    if not cleaned or cleaned == '.':
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


_DATE_RE = re.compile(r'^(\d{1,2})-([A-Za-z]{3})-(\d{2})$')
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def _parse_agbro_date(s: str) -> Optional[dt.date]:
    m = _DATE_RE.match(s or '')
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2).lower())
    year = 2000 + int(m.group(3))
    if not month:
        return None
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def fetch_agbro_latest() -> Optional[dict]:
    """Return dict keyed by AGBRO city name, plus 'egg_peti' PKR and 'row_date'.

    AGBRO renders the year as multiple monthly tables (Jan, Feb, Mar, Apr ...)
    on the same page. Earlier versions of this scraper only read the *first*
    table and therefore returned January data year-round. We now iterate every
    tableizer-table on the page, parse every date cell, and pick the row with
    the latest real calendar date.
    """
    try:
        # 2026 yearly archive page is the canonical source; homepage is fine
        # too because it redirects to the same content.
        candidates = [
            'https://www.agbro.com/broiler-market-prices-2026/',
            AGBRO_URL,
        ]
        html = None
        for url in candidates:
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

        latest_row = None
        latest_date: Optional[dt.date] = None
        for table in tables:
            for r in table.find_all('tr'):
                cells = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
                if not cells:
                    continue
                parsed = _parse_agbro_date(cells[0])
                if not parsed:
                    continue
                if latest_date is None or parsed > latest_date:
                    latest_date = parsed
                    latest_row = cells

        if not latest_row or len(latest_row) < 16:
            return None

        out: dict = {'row_date': latest_row[0]}
        for city, idx in AGBRO_COL_MAP.items():
            payload = {}
            for metric, i in idx.items():
                if i < len(latest_row):
                    v = _num(latest_row[i])
                    if v is not None:
                        payload[metric] = v
            if payload:
                out[city] = payload

        if len(latest_row) > AGBRO_EGG_PETI_IDX:
            peti = _num(latest_row[AGBRO_EGG_PETI_IDX])
            if peti and peti > 1000:  # peti price in thousands of PKR
                out['egg_peti'] = int(peti)

        return out if len(out) > 1 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Django admin override — manual rate entry takes priority.
# ---------------------------------------------------------------------------

def load_admin_override(region_key: str, today: str) -> Optional[MarketRate]:
    try:
        from api.models import MarketRateOverride  # local import to avoid app-loading issues
    except ImportError:
        return None
    try:
        row = MarketRateOverride.objects.filter(
            region_key=region_key, date=today, active=True
        ).order_by('-updated_at').first()
    except Exception:
        return None
    if not row:
        return None
    region_meta = next((r for r in REGIONS if r['key'] == region_key), None)
    if not region_meta:
        return None
    tray = int(row.egg_tray_price)
    return MarketRate(
        date=today,
        region=region_meta['name'],
        region_key=region_key,
        province=region_meta['province'],
        egg_tray_price=tray,
        egg_peti_price=tray * TRAYS_PER_PETI,
        broiler_live_per_kg=int(row.broiler_live_per_kg),
        broiler_meat_per_kg=int(row.broiler_live_per_kg * 1.52),
        doc_price=int(row.doc_price or 70),
        feed_starter_per_bag=int(row.feed_starter_per_bag or 9800),
        feed_grower_per_bag=int(row.feed_grower_per_bag or 9500),
        feed_finisher_per_bag=int(row.feed_finisher_per_bag or 9200),
        source='admin',
        scraped=True,
    )


# ---------------------------------------------------------------------------
# Per-region composer — admin → agbro → mirror → mock.
# ---------------------------------------------------------------------------

def compose_rate(region: dict, today: str, agbro: Optional[dict], composed: dict) -> MarketRate:
    # 1. Admin override wins.
    override = load_admin_override(region['key'], today)
    if override is not None:
        return override

    # 2. AGBRO direct.
    city = region['agbro_city']
    if city and agbro and city in agbro:
        city_data = agbro[city]
        live = int(city_data.get('farm') or _baseline(region['key'])['live'])
        doc = int(city_data.get('doc') or _baseline(region['key'])['doc'])
        peti = agbro.get('egg_peti')
        if peti:
            tray = peti // TRAYS_PER_PETI
            peti_price = peti
        else:
            tray = _baseline(region['key'])['tray']
            peti_price = tray * TRAYS_PER_PETI
        mock = mock_rate(region, today)  # for feed fallback
        return MarketRate(
            date=today,
            region=region['name'],
            region_key=region['key'],
            province=region['province'],
            egg_tray_price=tray,
            egg_peti_price=peti_price,
            broiler_live_per_kg=live,
            broiler_meat_per_kg=int(live * 1.52),
            doc_price=doc,
            feed_starter_per_bag=mock.feed_starter_per_bag,
            feed_grower_per_bag=mock.feed_grower_per_bag,
            feed_finisher_per_bag=mock.feed_finisher_per_bag,
            source='agbro.com',
            scraped=True,
            raw=city_data,
        )

    # 3. Mirror — reuse an already-composed sibling region.
    if region['mirror_of'] and region['mirror_of'] in composed:
        src = composed[region['mirror_of']]
        return MarketRate(
            date=today,
            region=region['name'],
            region_key=region['key'],
            province=region['province'],
            egg_tray_price=src.egg_tray_price,
            egg_peti_price=src.egg_peti_price,
            broiler_live_per_kg=src.broiler_live_per_kg,
            broiler_meat_per_kg=src.broiler_meat_per_kg,
            doc_price=src.doc_price,
            feed_starter_per_bag=src.feed_starter_per_bag,
            feed_grower_per_bag=src.feed_grower_per_bag,
            feed_finisher_per_bag=src.feed_finisher_per_bag,
            source=f'mirror:{region["mirror_of"]}',
            scraped=src.scraped,
        )

    # 4. Mock.
    return mock_rate(region, today)


# ---------------------------------------------------------------------------
# Firestore writer.
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

    # Main historical doc + latest pointer.
    db.collection('market_rates').document(doc_id).set(payload, merge=True)
    db.collection('market_rates_latest').document(rate.region_key).set(payload, merge=True)
    return f'market_rates/{doc_id}'


# ---------------------------------------------------------------------------
# Management command.
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Fetch daily poultry market rates (egg peti / broiler / feed) and write to Firestore.'

    def add_arguments(self, parser):
        parser.add_argument('--region', type=str, default=None,
                            help='Only process this region key. Defaults to all.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print payloads without writing to Firestore.')
        parser.add_argument('--date', type=str, default=None,
                            help='Override date (YYYY-MM-DD). Defaults to today (Asia/Karachi).')
        parser.add_argument('--skip-agbro', action='store_true',
                            help='Skip the AGBRO scraper (for offline testing).')

    def handle(self, *args, **options):
        # Asia/Karachi is UTC+5 — shift to local date so the "daily" job lines up
        # with the Pakistani market day rather than UTC midnight.
        today = options['date'] or (dt.datetime.utcnow() + dt.timedelta(hours=5)).strftime('%Y-%m-%d')
        target_key = options['region']
        dry_run = options['dry_run']

        regions = [r for r in REGIONS if not target_key or r['key'] == target_key]
        if not regions:
            raise CommandError(f'Unknown region: {target_key}')

        agbro = None
        if not options['skip_agbro']:
            self.stdout.write('Fetching AGBRO.com ...')
            agbro = fetch_agbro_latest()
            if agbro:
                cities = [k for k in agbro.keys() if k not in ('row_date', 'egg_peti')]
                self.stdout.write(self.style.SUCCESS(
                    f"  AGBRO OK — row_date={agbro.get('row_date')} "
                    f"egg_peti={agbro.get('egg_peti')} cities={cities}"
                ))
            else:
                self.stdout.write(self.style.WARNING('  AGBRO failed — falling back to mock/mirror.'))

        self.stdout.write(self.style.NOTICE(
            f'Composing rates for {len(regions)} region(s) — date={today} dry_run={dry_run}'
        ))

        composed: dict = {}
        for region in regions:
            rate = compose_rate(region, today, agbro, composed)
            composed[region['key']] = rate
            path = write_to_firestore(rate, dry_run=dry_run)
            tag = {
                'admin': 'ADMIN',
                'agbro.com': 'LIVE ',
                'mock_generator': 'MOCK ',
            }.get(rate.source, rate.source[:5].upper())
            self.stdout.write(
                f"  [{tag}] {rate.region:12s}  "
                f"tray=PKR {rate.egg_tray_price:>4}  peti=PKR {rate.egg_peti_price:>6}  "
                f"broiler={rate.broiler_live_per_kg:>4}/kg  doc={rate.doc_price:>4}  -> {path}"
            )
            if dry_run:
                self.stdout.write(json.dumps({**asdict(rate), 'raw': rate.raw}, indent=2, default=str))

        self.stdout.write(self.style.SUCCESS('Market rates refresh complete.'))
