import csv
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from api.models import Supplier, SupplierProduct


def _normalize_phone(value: str) -> str:
    digits = re.sub(r'[^0-9+]', '', (value or '').strip())
    if digits.startswith('00'):
        digits = f'+{digits[2:]}'
    if not digits.startswith('+') and digits:
        digits = f'+{digits}'
    return digits


def _to_bool(value: str, default: bool = True) -> bool:
    raw = (value or '').strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'y'}


class Command(BaseCommand):
    help = (
        'Import suppliers/products from CSV. Required supplier headers: '
        'name,supplier_type,phone,whatsapp,location. Optional: latitude,longitude,is_active, '
        'product_name,product_name_ur,price,unit,product_is_available'
    )

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Absolute/relative CSV file path')

    def handle(self, *args, **options):
        file_path = options['file']
        created_suppliers = 0
        updated_suppliers = 0
        created_products = 0
        updated_products = 0

        try:
            with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                required = {'name', 'supplier_type', 'phone', 'whatsapp', 'location'}
                if not required.issubset(set(reader.fieldnames or [])):
                    raise CommandError(
                        'CSV must contain headers: name,supplier_type,phone,whatsapp,location'
                    )

                for row in reader:
                    name = (row.get('name') or '').strip()
                    supplier_type = (row.get('supplier_type') or '').strip().lower()
                    phone = _normalize_phone(row.get('phone') or '')
                    whatsapp = _normalize_phone(row.get('whatsapp') or '')
                    location = (row.get('location') or '').strip()
                    latitude_raw = (row.get('latitude') or '').strip()
                    longitude_raw = (row.get('longitude') or '').strip()

                    if supplier_type not in {'feed', 'vaccine', 'equipment'}:
                        self.stdout.write(self.style.WARNING(f'Skipping invalid supplier_type row: {row}'))
                        continue
                    if not name or not whatsapp or not location:
                        self.stdout.write(self.style.WARNING(f'Skipping invalid row: {row}'))
                        continue

                    latitude = float(latitude_raw) if latitude_raw else None
                    longitude = float(longitude_raw) if longitude_raw else None
                    is_active = _to_bool(row.get('is_active'), default=True)

                    supplier, created = Supplier.objects.get_or_create(
                        name=name,
                        defaults={
                            'supplier_type': supplier_type,
                            'phone': phone,
                            'whatsapp': whatsapp,
                            'location': location,
                            'latitude': latitude,
                            'longitude': longitude,
                            'is_active': is_active,
                        },
                    )

                    if created:
                        created_suppliers += 1
                    else:
                        supplier.supplier_type = supplier_type
                        supplier.phone = phone
                        supplier.whatsapp = whatsapp
                        supplier.location = location
                        supplier.latitude = latitude
                        supplier.longitude = longitude
                        supplier.is_active = is_active
                        supplier.save(update_fields=[
                            'supplier_type', 'phone', 'whatsapp', 'location', 'latitude', 'longitude', 'is_active'
                        ])
                        updated_suppliers += 1

                    product_name = (row.get('product_name') or '').strip()
                    if not product_name:
                        continue

                    product_name_ur = (row.get('product_name_ur') or '').strip()
                    unit = (row.get('unit') or 'per unit').strip()
                    is_available = _to_bool(row.get('product_is_available'), default=True)
                    price_raw = (row.get('price') or '').strip()
                    try:
                        price = Decimal(price_raw)
                    except (InvalidOperation, TypeError):
                        self.stdout.write(self.style.WARNING(
                            f'Skipping product with invalid price ({price_raw}) for supplier {name}'
                        ))
                        continue

                    product, product_created = SupplierProduct.objects.get_or_create(
                        supplier=supplier,
                        name=product_name,
                        defaults={
                            'name_ur': product_name_ur,
                            'price': price,
                            'unit': unit,
                            'is_available': is_available,
                        },
                    )

                    if product_created:
                        created_products += 1
                    else:
                        product.name_ur = product_name_ur
                        product.price = price
                        product.unit = unit
                        product.is_available = is_available
                        product.save(update_fields=['name_ur', 'price', 'unit', 'is_available'])
                        updated_products += 1

        except FileNotFoundError as exc:
            raise CommandError(f'File not found: {file_path}') from exc

        self.stdout.write(self.style.SUCCESS(
            f'Suppliers import complete. suppliers_created={created_suppliers}, '
            f'suppliers_updated={updated_suppliers}, products_created={created_products}, '
            f'products_updated={updated_products}'
        ))
