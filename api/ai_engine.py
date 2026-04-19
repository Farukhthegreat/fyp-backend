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
    'Healthy': ['Flock appears healthy. Continue regular monitoring.',
                'Maintain clean water supply and proper ventilation.'],
    'Coccidiosis': ['ALERT: Coccidiosis detected. Isolate affected birds immediately.',
                    'Administer anticoccidial medication (e.g., Amprolium) in drinking water.',
                    'Replace litter completely. Disinfect feeders and waterers.'],
    'Salmonella': ['ALERT: Salmonella suspected. Practice strict biosecurity.',
                   'Wear gloves when handling birds. Send fecal samples for lab confirmation.',
                   'Isolate affected birds. Disinfect all equipment thoroughly.'],
    'Newcastle Disease': ['CRITICAL: Newcastle Disease detected. Highly contagious!',
                          'Quarantine entire house. Do NOT move birds between locations.',
                          'Report to local veterinary authority immediately.'],
    'Not Poultry Feces': ['Image does not appear to be poultry feces.',
                          'Retake the photo with a closer, clearer feces sample.'],
    'Uncertain': ['The sample is uncertain.',
                  'Retake a closer and sharper image of a single feces sample.'],
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
        # Keep payload size sane — the HF Space caps at these by default,
        # but pinning them means examiner uploads can't accidentally ask
        # for 300 frames and time the request out.
        'sample_fps': '1.0',
        'max_frames': '24',
        'max_boxes_per_frame': '4',
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            files=files,
            data=form_data,
            timeout=_INFERENCE_TIMEOUT * 2,  # video is slower than images
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
