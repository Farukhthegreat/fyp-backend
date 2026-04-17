#!/bin/bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_data

# Daily market-rate scraping is now handled by the separate Render Cron
# Job service (aviansense-scraper) on a $1/mo Starter plan. Keeping it
# out of the web deploy avoids slowing down restarts and prevents a
# broken scrape from stalling unrelated code pushes.
