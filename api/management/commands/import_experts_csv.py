import csv
import re

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from api.models import Expert


def _normalize_phone(value: str) -> str:
    digits = re.sub(r'[^0-9+]', '', (value or '').strip())
    if digits.startswith('00'):
        digits = f'+{digits[2:]}'
    if not digits.startswith('+') and digits:
        digits = f'+{digits}'
    return digits


class Command(BaseCommand):
    help = 'Import real experts from CSV file (name,specialization,phone,whatsapp,email,is_available)'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Absolute/relative CSV file path')

    def handle(self, *args, **options):
        file_path = options['file']

        created_users = 0
        created_experts = 0
        updated_experts = 0

        try:
            with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                required = {'name', 'specialization', 'phone', 'whatsapp'}
                if not required.issubset(set(reader.fieldnames or [])):
                    raise CommandError(
                        'CSV must contain headers: name,specialization,phone,whatsapp '
                        '(optional: email,is_available)'
                    )

                for row in reader:
                    name = (row.get('name') or '').strip()
                    specialization = (row.get('specialization') or '').strip()
                    phone = _normalize_phone(row.get('phone') or '')
                    whatsapp = _normalize_phone(row.get('whatsapp') or '')
                    email = (row.get('email') or '').strip().lower()
                    is_available = (row.get('is_available') or 'true').strip().lower() in {
                        '1', 'true', 'yes', 'y'
                    }

                    if not name or not specialization or not whatsapp:
                        self.stdout.write(self.style.WARNING(f'Skipping invalid row: {row}'))
                        continue

                    first_name = name.split()[0]
                    username_seed = email or whatsapp.replace('+', '') or re.sub(r'\W+', '', name.lower())
                    username = f'expert_{username_seed}'[:150]

                    user, user_created = User.objects.get_or_create(
                        username=username,
                        defaults={
                            'first_name': first_name,
                            'email': email,
                        },
                    )

                    if user_created:
                        created_users += 1
                        user.set_unusable_password()
                        user.save(update_fields=['password'])

                    expert, expert_created = Expert.objects.get_or_create(
                        user=user,
                        defaults={
                            'specialization': specialization,
                            'phone': phone,
                            'whatsapp': whatsapp,
                            'is_available': is_available,
                        },
                    )

                    if expert_created:
                        created_experts += 1
                    else:
                        expert.specialization = specialization
                        expert.phone = phone
                        expert.whatsapp = whatsapp
                        expert.is_available = is_available
                        expert.save(update_fields=['specialization', 'phone', 'whatsapp', 'is_available'])
                        updated_experts += 1

        except FileNotFoundError as exc:
            raise CommandError(f'File not found: {file_path}') from exc

        self.stdout.write(self.style.SUCCESS(
            f'Experts import complete. users_created={created_users}, '
            f'experts_created={created_experts}, experts_updated={updated_experts}'
        ))
