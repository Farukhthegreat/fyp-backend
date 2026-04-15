import os
import random
import requests


# Demo mode disease pool (used when AI_INFERENCE_URL is not configured)
_DEMO_DISEASES = [
    ('Healthy', 72), ('Healthy', 75), ('Healthy', 80), ('Healthy', 85),
    ('Healthy', 91), ('Healthy', 94), ('Healthy', 97),
    ('Newcastle Disease', 78), ('Newcastle Disease', 84),
    ('Coccidiosis', 88), ('Coccidiosis', 73),
    ('Salmonella', 82), ('Salmonella', 76),
]

# Disease-specific tips for demo mode and fallback
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
}


def fetch_weather(lat, lon):
    """Fetch current weather from Open-Meteo (free, no API key needed).
    Returns dict with temperature, humidity, wind_speed, pressure.
    Returns defaults if fetch fails."""
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


def _demo_predict(image_file):
    """Demo mode: returns a realistic-looking result based on image content hash."""
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
    }


def predict_disease(image_file, weather=None):
    """Call external AI service for poultry disease diagnosis.

    Args:
        image_file: uploaded image file
        weather: dict with temperature, humidity, wind_speed, pressure (optional)

    If AI_INFERENCE_URL is not set, runs in demo mode.
    """
    endpoint = os.getenv('AI_INFERENCE_URL', '').strip()

    if not endpoint:
        return _demo_predict(image_file)

    api_key = os.getenv('AI_INFERENCE_API_KEY', '').strip()
    image_file.seek(0)
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    files = {
        'image': (image_file.name, image_file.read(), image_file.content_type or 'application/octet-stream')
    }

    # Pass environmental data as form fields
    w = weather or {}
    form_data = {
        'temperature': str(w.get('temperature', 25.0)),
        'humidity': str(w.get('humidity', 50.0)),
        'wind_speed': str(w.get('wind_speed', 5.0)),
        'pressure': str(w.get('pressure', 1010.0)),
        'ammonia': '10.0',  # Not available from weather API
    }

    try:
        response = requests.post(endpoint, headers=headers, files=files,
                                 data=form_data, timeout=120)
    except requests.RequestException as exc:
        raise RuntimeError(f'AI inference request failed: {exc}') from exc

    if response.status_code != 200:
        raise RuntimeError(f'AI inference service returned HTTP {response.status_code}')

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

    result = {
        'disease_name': disease_name.strip(),
        'confidence': round(float(confidence), 1),
    }
    if isinstance(payload.get('all_probabilities'), dict):
        result['all_probabilities'] = payload['all_probabilities']
    if isinstance(payload.get('tips'), list):
        result['tips'] = payload['tips']
    else:
        result['tips'] = _TIPS.get(disease_name.strip(), _TIPS.get('Healthy', []))

    return result
