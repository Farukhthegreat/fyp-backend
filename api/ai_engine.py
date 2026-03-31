import os
import requests


def predict_disease(image_file):
    """Call a real external AI service for poultry diagnosis.

    Required env vars:
      - AI_INFERENCE_URL: HTTP endpoint that accepts multipart image upload
    Optional env vars:
      - AI_INFERENCE_API_KEY: bearer token sent as Authorization header

    Expected JSON response:
      {
        "disease_name": "Healthy",
        "confidence": 97.3
      }
    """
    endpoint = os.getenv('AI_INFERENCE_URL')
    api_key = os.getenv('AI_INFERENCE_API_KEY', '').strip()

    if not endpoint:
        raise RuntimeError(
            'AI inference is not configured. Set AI_INFERENCE_URL in environment variables.'
        )

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
