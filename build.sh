#!/bin/bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_data

# Fetch today's Punjab Market Committee poultry rates.
# Runs on every deploy, including the daily GitHub-Actions → Render deploy-hook
# ping. Uses `|| true` so a transient scrape failure (OCR.space rate limit,
# Punjab site down, etc.) never blocks the web deploy itself.
python manage.py fetch_market_rates || true
