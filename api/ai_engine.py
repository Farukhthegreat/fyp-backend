"""
AI engine — thin proxy between Django and the Hugging Face Space that
hosts the trained YOLO + DINOv2 + XGBoost fusion pipeline.

Set `AI_INFERENCE_URL` to the Space's `/predict` endpoint
(e.g., `https://farrukh1122-aviansense-inference.hf.space/predict`).
When that env var is empty we fall back to a deterministic demo mode so
local development and CI still work without a live model server.
"""

import os
import random
import requests


# --------------------------------------------------------------------------
# Demo mode
# --------------------------------------------------------------------------

_DEMO_DISEASES = [
    ('Healthy', 72), ('Healthy', 75), ('Healthy', 80), ('Healthy', 85),
    ('Healthy', 91), ('Healthy', 94), ('Healthy', 97),
    ('Newcastle Disease', 78), ('Newcastle Disease', 84),
    ('Coccidiosis', 88), ('Coccidiosis', 73),
    ('Salmonella', 82), ('Salmonella', 76),
]

_TIPS = {
    'Healthy': [
        'No disease markers detected. Continue your current flock management plan.',
        'Daily watch points: observe feed intake, water consumption, droppings, breathing, and comb colour. A sudden drop in any signals early illness.',
        'Biosecurity: restrict farm visitors, sanitise boots/hands between houses, and clean waterers every 24 hours.',
        'Schedule routine vaccinations (Newcastle, Gumboro) per your vet\'s calendar — prevention beats treatment.',
        'Recheck the flock in 3-5 days or sooner if any bird becomes lethargic, stops eating, or breathes heavily.',
    ],
    'Coccidiosis': [
        'Clinical signs to confirm: bloody or mucus-streaked droppings, ruffled feathers, drop in feed intake, huddling near heat, pale comb, reduced weight gain.',
        'First-line treatment: Amprolium 20% in drinking water at 0.024% (24 ml of 20% solution per 100 L water) for 5-7 days. Consult your vet before dosing — strengths vary by brand.',
        'Supportive care: add electrolytes + vitamin A and K3 to water for 3-5 days to rebuild gut lining and help blood clotting.',
        'House hygiene: remove wet litter immediately, replace with dry fresh bedding, and disinfect drinkers daily with a coccidiostat-safe sanitiser (not chlorine bleach while medicating).',
        'Isolate affected birds in a separate pen. Coccidia oocysts spread through droppings — keep equipment and footwear dedicated to the sick pen.',
        'If no improvement in 72 hours, or if mortality climbs past 2 birds/day per 1000, escalate to a qualified poultry veterinarian immediately.',
        'Prevention after recovery: switch starter/grower feed with a coccidiostat (monensin, salinomycin) until 14 days before slaughter; keep litter dry at all times.',
    ],
    'Salmonella': [
        'Suspect signs: yellow/greenish diarrhoea, sudden drop in egg production, lethargy, pale comb, huddling, sudden deaths in young birds. Zoonotic — handle with care.',
        'Immediate isolation: separate affected birds. Cull visibly weak birds humanely and bury or incinerate — do not sell or butcher.',
        'Antibiotic treatment: only after a vet-ordered cloacal swab or faecal culture confirms the serovar. Typical first-line is Enrofloxacin 10% (10 mg/kg body weight in drinking water for 3-5 days) — dosage must be confirmed by a licensed vet.',
        'Never administer antibiotics prophylactically to a flock entering slaughter age — observe the full withdrawal period (at least 7-10 days for Enrofloxacin).',
        'Hygiene protocol: gloves + mask when handling, disinfect boots with 0.5% sodium hypochlorite, wash hands with soap after every pen visit.',
        'Hydration and gut support: add probiotic (Lactobacillus) + oral electrolyte to water for 7 days. Reduces shedding and helps gut re-colonise with normal flora.',
        'Report the outbreak to your district veterinary officer — Salmonella is reportable in Pakistan and your neighbours may be affected.',
        'Post-recovery: perform full house cleanout, insect/rodent control (they carry Salmonella), and consider vaccinating future flocks with killed Salmonella vaccine.',
    ],
    'Newcastle Disease': [
        'CRITICAL alert: Newcastle Disease is highly contagious and notifiable. Do not move birds, eggs, feed, or equipment off the farm.',
        'Clinical signs to confirm: gasping, twisted neck (torticollis), greenish watery diarrhoea, sudden drop in egg production, soft-shelled eggs, tremors, paralysis.',
        'There is no specific antiviral cure. Treatment is purely supportive while the flock either recovers or is depopulated per veterinary direction.',
        'Supportive care: multivitamin + electrolyte solution in drinking water for 7-10 days; maintain feed access even if intake drops.',
        'Immediately vaccinate any unaffected birds with LaSota or I-2 Newcastle vaccine via drinking water or eye drop (consult vet for exact schedule).',
        'Quarantine: shut the farm to visitors and outside transport. Disinfect vehicles with 2% sodium hydroxide or 0.5% sodium hypochlorite.',
        'Contact your district veterinary officer and the Poultry Research Institute TODAY. Delay costs neighbouring flocks.',
        'Post-outbreak: 14-day downtime after last mortality, full disinfection (walls, floor, feeders), then restart with NDV-vaccinated day-old chicks.',
    ],
    'Not Poultry Feces': [
        'This image did not match a poultry droppings sample.',
        'Take a fresh close-up: single fresh dropping, 15-25 cm from the camera, bright natural light, clean contrasting background.',
        'Avoid blurry, shadowed, or angled shots. The model needs sharp texture detail to diagnose.',
    ],
    'Uncertain': [
        'The sample was too ambiguous for a confident diagnosis.',
        'Retake with a closer, better-lit shot of a single fresh dropping.',
        'If the birds show clinical signs (lethargy, watery droppings, drop in feed) despite an uncertain image, consult your local vet rather than wait for a clean image.',
    ],
}


def _demo_predict(image_file):
    """Deterministic stand-in when no HF Space is wired up yet."""
    image_file.seek(0)
    data = image_file.read(4096)
    seed = sum(data) if data else 42
    rng = random.Random(seed)
    weights = [7, 7, 6, 5, 4, 3, 2, 3, 2, 2, 2, 2, 2]
    choice_idx = rng.choices(range(len(_DEMO_DISEASES)), weights=weights, k=1)[0]
    disease_name, base_conf = _DEMO_DISEASES[choice_idx]
    confidence = round(base_conf + rng.uniform(-2.0, 2.0), 1)
    confidence = max(70.0, min(99.0, confidence))
    return {
        'disease_name': disease_name,
        'confidence': confidence,
        'tips': _TIPS.get(disease_name, _TIPS['Healthy']),
        'pipeline': 'demo',
        'accepted': True,
        'rejected': False,
    }


# --------------------------------------------------------------------------
# Weather helper (unchanged — external public API, no key required)
# --------------------------------------------------------------------------

def fetch_weather(lat, lon):
    """Fetch current weather from Open-Meteo. Returns defaults if fetch fails."""
    defaults = {'temperature': 25.0, 'humidity': 50.0, 'wind_speed': 5.0, 'pressure': 1010.0}
    if not lat or not lon:
        return defaults
    try:
        url = (
            f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}'
            f'&current=temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure'
        )
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return defaults
        data = resp.json().get('current', {})
        return {
            'temperature': data.get('temperature_2m', 25.0),
            'humidity': data.get('relative_humidity_2m', 50.0),
            'wind_speed': data.get('wind_speed_10m', 5.0),
            'pressure': data.get('surface_pressure', 1010.0),
        }
    except Exception:
        return defaults


# --------------------------------------------------------------------------
# HF Space proxy
# --------------------------------------------------------------------------

# HF CPU Basic inference can take 5–10s per image, and a cold start after 48 h
# idle adds ~30 s on top. 180 s gives us comfortable headroom without blocking
# the Django worker forever.
_INFERENCE_TIMEOUT = float(os.getenv('AI_INFERENCE_TIMEOUT', '180'))

# Fields the Space may return that the app should see verbatim. Anything not
# in this list is dropped so unknown server-side metadata doesn't leak
# through to the client unintentionally.
_PASSTHROUGH_FIELDS = (
    'accepted',
    'rejected',
    'gate_failed',
    'reason',
    'disease_name',
    'confidence',
    'all_probabilities',
    'image_stage_probabilities',
    'image_stage_top_class',
    'image_stage_top_confidence',
    'yolo_detected',
    'yolo_confidence',
    'crop_used',
    'crop_preview_data_url',
    'bbox',
    'audio_details',
    'environment',
    'tips',
    'pipeline',
    'xai',
)


def predict_disease(image_file, weather=None):
    """Call the configured HF Space / inference service.

    Args:
        image_file: Django ``UploadedFile`` from the request.
        weather: optional dict with temperature, humidity, wind_speed, pressure.

    Returns a dict suitable for both the Flutter client and our Django
    ``DiagnosisResult`` row. When ``AI_INFERENCE_URL`` isn't set we return a
    deterministic demo response so the rest of the stack keeps working.
    """
    endpoint = os.getenv('AI_INFERENCE_URL', '').strip()
    if not endpoint:
        return _demo_predict(image_file)

    api_key = os.getenv('AI_INFERENCE_API_KEY', '').strip()
    image_file.seek(0)

    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    # Buffer the bytes so we can rewind the Django UploadedFile afterwards —
    # views.py still needs to persist the same file on the DiagnosisResult
    # row when the sample is accepted.
    image_bytes = image_file.read()
    image_file.seek(0)

    files = {
        'image': (
            image_file.name,
            image_bytes,
            image_file.content_type or 'application/octet-stream',
        ),
    }

    w = weather or {}
    form_data = {
        'temperature': str(w.get('temperature', 25.0)),
        'humidity':    str(w.get('humidity', 50.0)),
        'wind_speed':  str(w.get('wind_speed', 5.0)),
        'pressure':    str(w.get('pressure', 1010.0)),
        'ammonia':     '10.0',      # no weather provider exposes this
        'use_uploaded_audio': 'false',
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            files=files,
            data=form_data,
            timeout=_INFERENCE_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f'AI inference request failed: {exc}') from exc

    if response.status_code != 200:
        raise RuntimeError(
            f'AI inference service returned HTTP {response.status_code}: '
            f'{response.text[:400]}'
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError('AI inference response is not valid JSON') from exc

    disease_name = payload.get('disease_name')
    confidence = payload.get('confidence')

    if not isinstance(disease_name, str) or not disease_name.strip():
        raise RuntimeError('AI inference response missing valid disease_name')
    if not isinstance(confidence, (int, float)):
        raise RuntimeError('AI inference response missing valid confidence')

    result = {k: payload[k] for k in _PASSTHROUGH_FIELDS if k in payload}
    result['disease_name'] = disease_name.strip()
    result['confidence'] = round(float(confidence), 1)

    if 'tips' not in result or not isinstance(result.get('tips'), list):
        result['tips'] = _TIPS.get(result['disease_name'], _TIPS.get('Healthy', []))

    # Backward-compatible defaults for old Flutter builds that don't know
    # about the new rejection fields.
    result.setdefault('accepted', True)
    result.setdefault('rejected', False)

    return result


# --------------------------------------------------------------------------
# Video inference proxy
# --------------------------------------------------------------------------

def _video_endpoint():
    """Derive /analyze-video from AI_INFERENCE_URL so operators only have to
    configure one env var."""
    base = os.getenv('AI_INFERENCE_URL', '').strip()
    if not base:
        return ''
    # Strip trailing segment (usually /predict) and append /analyze-video.
    if base.endswith('/'):
        base = base.rstrip('/')
    if '/' in base.split('://', 1)[-1]:
        host, _, _ = base.rpartition('/')
        return f'{host}/analyze-video'
    return f'{base}/analyze-video'


def predict_video(video_file, weather=None):
    """Call the HF Space /analyze-video endpoint. Returns the full JSON
    response (frame reports, diagnosis counts, XAI summary, annotated video
    URL) so the Flutter client can render the monitoring view directly.

    Falls back to a short demo payload if AI_INFERENCE_URL is unset so local
    dev doesn't crash.
    """
    endpoint = _video_endpoint()
    if not endpoint:
        # Minimal demo so the UI path can still be exercised locally.
        return {
            'status': 'demo',
            'analysis_mode': 'uploaded_video_monitoring',
            'top_diagnosis': 'Healthy',
            'diagnosis_counts': {'Healthy': 1},
            'processed_frames': 1,
            'source_duration_sec': 0.0,
            'frame_reports': [],
            'xai_summary': {'method': 'demo', 'note': 'No HF endpoint configured.'},
        }

    api_key = os.getenv('AI_INFERENCE_API_KEY', '').strip()
    video_file.seek(0)
    video_bytes = video_file.read()
    video_file.seek(0)

    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    files = {
        'video': (
            video_file.name,
            video_bytes,
            video_file.content_type or 'video/mp4',
        ),
    }

    w = weather or {}
    form_data = {
        'temperature': str(w.get('temperature', 25.0)),
        'humidity':    str(w.get('humidity', 50.0)),
        'wind_speed':  str(w.get('wind_speed', 5.0)),
        'pressure':    str(w.get('pressure', 1010.0)),
        'ammonia':     '10.0',
        'use_uploaded_audio': 'false',
        # Match the lighter standalone tester profile. The earlier 24-frame /
        # 4-box setup was noticeably slower on Render -> HF CPU and made the
        # mobile app feel hung on ordinary phone clips.
        'sample_fps': '1.0',
        'max_frames': '12',
        'max_boxes_per_frame': '2',
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            files=files,
            data=form_data,
            timeout=(30, 180),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f'AI video request failed: {exc}') from exc

    if response.status_code != 200:
        raise RuntimeError(
            f'AI video service returned HTTP {response.status_code}: '
            f'{response.text[:400]}'
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError('AI video response is not valid JSON') from exc

    if not isinstance(payload, dict):
        raise RuntimeError('AI video response must be a JSON object')

    return payload
