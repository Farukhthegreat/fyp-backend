import time
import random


def predict_disease(image_file):
    """
    Mock AI engine that simulates disease prediction for poultry images.

    Args:
        image_file: The uploaded image file

    Returns:
        dict: Contains 'disease_name' and 'confidence' keys
    """
    # Simulate AI processing time
    time.sleep(1.5)

    # List of mock poultry diseases
    diseases = [
        'Newcastle Disease',
        'Avian Influenza',
        'Infectious Bronchitis',
        'Marek\'s Disease',
        'Fowl Pox',
        'Coccidiosis',
        'Healthy',
        'Infectious Bursal Disease',
        'Salmonellosis',
        'Colibacillosis'
    ]

    # Randomly select a disease
    disease_name = random.choice(diseases)

    # Generate random confidence between 85-99.5
    confidence = round(random.uniform(85.0, 99.5), 1)

    return {
        'disease_name': disease_name,
        'confidence': confidence
    }
