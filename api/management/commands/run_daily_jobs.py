"""Cron entrypoint that chains the three daily jobs.

The Render cron service ``aviansense-scraper`` previously only ran the
market-rate scraper. We now chain the auto-tip generator and the morning
brief into the same cron run so the project still uses a single
$1/mo Render Cron Job instead of three separate ones. Each step is
isolated — a Gemini hiccup on one step never blocks the others.

Render cron command:
    python manage.py run_daily_jobs
"""
from __future__ import annotations

import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the daily AvianSense cron pipeline (market rates, tip, brief).'

    def add_arguments(self, parser):
        parser.add_argument('--skip-rates', action='store_true',
                            help='Skip the Punjab market-rate scrape.')
        parser.add_argument('--skip-tip', action='store_true',
                            help='Skip the Gemini auto-tip generator.')
        parser.add_argument('--skip-brief', action='store_true',
                            help='Skip the FCM daily-brief push.')

    def handle(self, *args, **options):
        skip_rates = options['skip_rates']
        skip_tip = options['skip_tip']
        skip_brief = options['skip_brief']

        if not skip_rates:
            self.stdout.write(self.style.NOTICE('==> fetch_market_rates'))
            try:
                call_command('fetch_market_rates')
            except Exception:
                logger.exception('fetch_market_rates failed')
                self.stdout.write(self.style.WARNING(
                    '  fetch_market_rates raised — continuing.'
                ))

        if not skip_tip:
            self.stdout.write(self.style.NOTICE('==> generate_daily_tip'))
            try:
                call_command('generate_daily_tip')
            except Exception:
                logger.exception('generate_daily_tip failed')
                self.stdout.write(self.style.WARNING(
                    '  generate_daily_tip raised — continuing.'
                ))

        if not skip_brief:
            self.stdout.write(self.style.NOTICE('==> send_daily_brief'))
            try:
                call_command('send_daily_brief')
            except Exception:
                logger.exception('send_daily_brief failed')
                self.stdout.write(self.style.WARNING(
                    '  send_daily_brief raised — continuing.'
                ))

        self.stdout.write(self.style.SUCCESS('Daily cron pipeline complete.'))
