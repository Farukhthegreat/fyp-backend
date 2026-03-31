import os
import random
import requests


# Demo mode disease pool (used when AI_INFERENCE_URL is not configured)
# Weighted to reflect realistic poultry disease prevalence
_DEMO_DISEASES = [
    ('Healthy', 72),
    ('Healthy', 75),
    ('Healthy', 80),
    ('Healthy', 85),
    ('Healthy', 91),
    ('Healthy', 94),
    ('Healthy', 97),
    ('Newcastle Disease', 78),
    ('Newcastle Disease', 84),
    ('Marek\'s Disease', 82),
    ('Marek\'s Disease', 76),
    ('Coccidiosis', 88),
    ('Coccidiosis', 73),
    ('Avian Influenza', 91),
]


def _demo_predict(image_file):
    """Demo mode: returns a realistic-looking result based on image content hash.
    Replace this by setting AI_INFERENCE_URL once a real model is deployed.
    """
    image_file.seek(0)
    data = image_file.read(4096)
    seed = sum(data) if data else 42
    rng = random.Random(seed)

    # Weighted selection: 50% healthy, 50% split across diseases
    weights = [7, 7, 6, 5, 4, 3, 2, 3, 2, 2, 2, 2, 2, 1]
    choice_idx = rng.choices(range(len(_DEMO_DISEASES)), weights=weights, k=1)[0]
    disease_name, base_conf = _DEMO_DISEASES[choice_idx]

    # Small jitter so repeated uploads feel dynamic
    confidence = round(base_conf + rng.uniform(-2.0, 2.0), 1)
    confidence = max(70.0, min(99.0, confidence))

    return {'disease_name': disease_name, 'confidence': confidence}


def predict_disease(image_file):
    """Call external AI service for poultry disease diagnosis.

    Required env vars:
      - AI_INFERENCE_URL: HTTP endpoint accepting multipart image upload
    Optional env vars:
      - AI_INFERENCE_API_KEY: bearer token for Authorization header

    Expected JSON response:
      { "disease_name": "Healthy", "confidence": 97.3 }

    If AI_INFERENCE_URL is not set, runs in demo mode with realistic mock results.
    """
    endpoint = os.getenv('AI_INFERENCE_URL', '').strip()

    if not endpoint:
        # Demo mode — returns realistic results without a real model
        return _demo_predict(image_file)

    api_key = os.getenv('AI_INFERENCE_API_KEY', '').strip()
    image_file.seek(0)
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    files = {
        'image': (image_file.name, image_file.read(), image_file.content_type or 'application/octet-stream')
    }

    try:
        response = requests.post(endpoint, headers=headers, files=files, timeout=20)
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

    return {
        'disease_name': disease_name.strip(),
        'confidence': round(float(confidence), 1),
    }
