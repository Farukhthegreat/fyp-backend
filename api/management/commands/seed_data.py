from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import (
    Supplier, SupplierProduct, Expert, DailyTask, Article
)


class Command(BaseCommand):
    help = 'Seed database with initial data for suppliers, experts, tasks, and articles'

    def handle(self, *args, **options):
        self.seed_suppliers()
        self.seed_experts()
        self.seed_tasks()
        self.seed_articles()
        self.stdout.write(self.style.SUCCESS('Seed data created successfully!'))

    def seed_suppliers(self):
        suppliers_data = [
            {
                'name': 'GT Road Feeds', 'supplier_type': 'feed',
                'phone': '+923001234567', 'whatsapp': '+923001234567',
                'location': 'GT Road, Rawalpindi', 'latitude': 33.5651, 'longitude': 73.0169,
                'products': [
                    {'name': 'Starter Feed (0-2 weeks)', 'name_ur': 'اسٹارٹر فیڈ', 'price': 4500, 'unit': 'per 50kg bag'},
                    {'name': 'Grower Feed (3-5 weeks)', 'name_ur': 'گروور فیڈ', 'price': 4200, 'unit': 'per 50kg bag'},
                    {'name': 'Finisher Feed (6+ weeks)', 'name_ur': 'فنشر فیڈ', 'price': 4000, 'unit': 'per 50kg bag'},
                ]
            },
            {
                'name': 'Islamabad Poultry Supplies', 'supplier_type': 'feed',
                'phone': '+923009876543', 'whatsapp': '+923009876543',
                'location': 'I-9 Industrial Area, Islamabad', 'latitude': 33.6844, 'longitude': 72.9979,
                'products': [
                    {'name': 'Layer Feed', 'name_ur': 'لیئر فیڈ', 'price': 4300, 'unit': 'per 50kg bag'},
                    {'name': 'Broiler Feed Premium', 'name_ur': 'بروئلر فیڈ پریمیم', 'price': 4800, 'unit': 'per 50kg bag'},
                ]
            },
            {
                'name': 'Punjab Veterinary Centre', 'supplier_type': 'vaccine',
                'phone': '+923005551234', 'whatsapp': '+923005551234',
                'location': 'Saddar, Rawalpindi', 'latitude': 33.5969, 'longitude': 73.0528,
                'products': [
                    {'name': 'Newcastle Disease Vaccine', 'name_ur': 'نیوکیسل ویکسین', 'price': 250, 'unit': 'per 100 doses'},
                    {'name': 'Gumboro Vaccine', 'name_ur': 'گمبورو ویکسین', 'price': 300, 'unit': 'per 100 doses'},
                    {'name': 'Fowl Pox Vaccine', 'name_ur': 'فاؤل پاکس ویکسین', 'price': 350, 'unit': 'per 100 doses'},
                ]
            },
            {
                'name': 'Rawalpindi Agri Equipment', 'supplier_type': 'equipment',
                'phone': '+923007778899', 'whatsapp': '+923007778899',
                'location': 'Asghar Mall Road, Rawalpindi', 'latitude': 33.5880, 'longitude': 73.0455,
                'products': [
                    {'name': 'Automatic Drinker', 'name_ur': 'آٹومیٹک پانی دینے والا', 'price': 1500, 'unit': 'per piece'},
                    {'name': 'Feed Tray (Round)', 'name_ur': 'فیڈ ٹرے', 'price': 800, 'unit': 'per piece'},
                    {'name': 'Heat Lamp', 'name_ur': 'ہیٹ لیمپ', 'price': 2500, 'unit': 'per piece'},
                ]
            },
            {
                'name': 'Attock Poultry Farm Supplies', 'supplier_type': 'feed',
                'phone': '+923001112233', 'whatsapp': '+923001112233',
                'location': 'Kamra Road, Attock', 'latitude': 33.7667, 'longitude': 72.3597,
                'products': [
                    {'name': 'Organic Poultry Feed', 'name_ur': 'آرگینک فیڈ', 'price': 5200, 'unit': 'per 50kg bag'},
                    {'name': 'Mineral Supplement', 'name_ur': 'منرل سپلیمنٹ', 'price': 1200, 'unit': 'per kg'},
                ]
            },
        ]

        for s_data in suppliers_data:
            products = s_data.pop('products')
            supplier, _ = Supplier.objects.get_or_create(
                name=s_data['name'], defaults=s_data
            )
            for p_data in products:
                SupplierProduct.objects.get_or_create(
                    supplier=supplier, name=p_data['name'], defaults=p_data
                )
        self.stdout.write(f'  Created {len(suppliers_data)} suppliers')

    def seed_experts(self):
        experts_data = [
            {
                'username': 'dr_ahmed', 'first_name': 'Dr. Ahmed',
                'email': 'ahmed@example.com',
                'specialization': 'Poultry Disease Specialist',
                'specialization_urdu': 'پولٹری امراض کے ماہر',
                'whatsapp': '+923001234568', 'phone': '+923001234568',
            },
            {
                'username': 'dr_fatima', 'first_name': 'Dr. Fatima',
                'email': 'fatima@example.com',
                'specialization': 'Avian Nutrition Expert',
                'specialization_urdu': 'مرغیوں کی غذائیت کے ماہر',
                'whatsapp': '+923009876544', 'phone': '+923009876544',
            },
            {
                'username': 'dr_hassan', 'first_name': 'Dr. Hassan',
                'email': 'hassan@example.com',
                'specialization': 'Poultry Farm Management',
                'specialization_urdu': 'پولٹری فارم انتظام',
                'whatsapp': '+923005551235', 'phone': '+923005551235',
            },
            {
                'username': 'dr_ayesha', 'first_name': 'Dr. Ayesha',
                'email': 'ayesha@example.com',
                'specialization': 'Veterinary Surgeon',
                'specialization_urdu': 'جانوروں کے ڈاکٹر (سرجن)',
                'whatsapp': '+923007778900', 'phone': '+923007778900',
            },
            {
                'username': 'dr_khalid', 'first_name': 'Dr. Khalid',
                'email': 'khalid@example.com',
                'specialization': 'Broiler Health Advisor',
                'specialization_urdu': 'برائلر صحت کے ماہر',
                'city': 'Sialkot',
                'city_urdu': 'سیالکوٹ',
                'whatsapp': '+923331112220', 'phone': '+923331112220',
            },
            {
                'username': 'dr_sara', 'first_name': 'Dr. Sara',
                'email': 'sara@example.com',
                'specialization': 'Layer Farm Consultant',
                'specialization_urdu': 'لیئر فارم کے مشیر',
                'city': 'Multan',
                'city_urdu': 'ملتان',
                'whatsapp': '+923441112220', 'phone': '+923441112220',
            },
            {
                'username': 'dr_taha', 'first_name': 'Dr. Taha',
                'email': 'taha@example.com',
                'specialization': 'Poultry Disease Specialist',
                'specialization_urdu': 'پولٹری امراض کے ماہر',
                'whatsapp': '+923221112220', 'phone': '+923221112220',
            },
        ]

        for e_data in experts_data:
            user, _ = User.objects.get_or_create(
                username=e_data['username'],
                defaults={
                    'first_name': e_data['first_name'],
                    'email': e_data['email'],
                }
            )
            defaults = {
                'specialization': e_data['specialization'],
                'specialization_urdu': e_data.get('specialization_urdu', ''),
                'whatsapp': e_data['whatsapp'],
                'phone': e_data['phone'],
            }
            if 'city' in e_data:
                defaults['city'] = e_data['city']
            if 'city_urdu' in e_data:
                defaults['city_urdu'] = e_data['city_urdu']
            obj, created = Expert.objects.get_or_create(
                user=user,
                defaults=defaults,
            )
            # Backfill Urdu fields on existing rows so re-seeding refreshes
            # older records that predate the Urdu columns.
            if not created and not obj.specialization_urdu:
                obj.specialization_urdu = e_data.get('specialization_urdu', '')
                if e_data.get('city_urdu'):
                    obj.city_urdu = e_data['city_urdu']
                obj.save(update_fields=['specialization_urdu', 'city_urdu'])
        self.stdout.write(f'  Created {len(experts_data)} experts')

    def seed_tasks(self):
        tasks_data = [
            {'name': 'Check water supply', 'name_ur': 'پانی کی فراہمی چیک کریں', 'category': 'water', 'time_of_day': 'morning', 'season': 'all', 'description': 'Ensure clean water is available in all drinkers', 'description_ur': 'تمام پینے والوں میں صاف پانی دستیاب ہونا یقینی بنائیں'},
            {'name': 'Fill feeders', 'name_ur': 'فیڈر بھریں', 'category': 'feed', 'time_of_day': 'morning', 'season': 'all', 'description': 'Fill all feeders with appropriate feed', 'description_ur': 'تمام فیڈر مناسب خوراک سے بھریں'},
            {'name': 'Collect eggs', 'name_ur': 'انڈے جمع کریں', 'category': 'egg', 'time_of_day': 'morning', 'season': 'all', 'description': 'Collect eggs from all nesting boxes', 'description_ur': 'تمام نیسٹنگ باکسز سے انڈے جمع کریں', 'min_flock_size': 10},
            {'name': 'Check temperature', 'name_ur': 'درجہ حرارت چیک کریں', 'category': 'temperature', 'time_of_day': 'morning', 'season': 'all', 'description': 'Monitor shed temperature and adjust ventilation', 'description_ur': 'شیڈ کا درجہ حرارت مانیٹر کریں اور وینٹیلیشن ایڈجسٹ کریں'},
            {'name': 'Afternoon water check', 'name_ur': 'دوپہر پانی چیک کریں', 'category': 'water', 'time_of_day': 'afternoon', 'season': 'all', 'description': 'Refill drinkers and check water quality', 'description_ur': 'پینے والے دوبارہ بھریں اور پانی کا معیار چیک کریں'},
            {'name': 'Health inspection', 'name_ur': 'صحت کا معائنہ', 'category': 'health', 'time_of_day': 'afternoon', 'season': 'all', 'description': 'Walk through flock and observe for signs of illness', 'description_ur': 'ریوڑ میں چل کر بیماری کی علامات دیکھیں'},
            {'name': 'Second feeding', 'name_ur': 'دوسری خوراک', 'category': 'feed', 'time_of_day': 'afternoon', 'season': 'all', 'description': 'Top up feeders for afternoon consumption', 'description_ur': 'دوپہر کی خوراک کے لیے فیڈر بھریں'},
            {'name': 'Adjust lighting', 'name_ur': 'لائٹنگ ایڈجسٹ کریں', 'category': 'light', 'time_of_day': 'evening', 'season': 'winter', 'description': 'Turn on supplemental lighting for winter', 'description_ur': 'سردیوں کے لیے اضافی روشنی آن کریں'},
            {'name': 'Evening egg collection', 'name_ur': 'شام کے انڈے جمع کریں', 'category': 'egg', 'time_of_day': 'evening', 'season': 'all', 'description': 'Final egg collection for the day', 'description_ur': 'دن کے لیے آخری انڈے جمع کریں', 'min_flock_size': 10},
            {'name': 'Secure shed', 'name_ur': 'شیڈ محفوظ کریں', 'category': 'cleaning', 'time_of_day': 'evening', 'season': 'all', 'description': 'Close doors, check ventilation, secure predator guards', 'description_ur': 'دروازے بند کریں، وینٹیلیشن چیک کریں'},
            {'name': 'Clean drinkers', 'name_ur': 'پینے والے صاف کریں', 'category': 'cleaning', 'time_of_day': 'morning', 'season': 'summer', 'description': 'Disinfect drinkers daily in summer to prevent bacteria', 'description_ur': 'گرمیوں میں بیکٹیریا سے بچنے کے لیے روزانہ صاف کریں'},
            {'name': 'Add electrolytes to water', 'name_ur': 'پانی میں الیکٹرولائٹس ڈالیں', 'category': 'water', 'time_of_day': 'morning', 'season': 'summer', 'description': 'Add electrolytes to prevent heat stress', 'description_ur': 'گرمی کے تناؤ سے بچنے کے لیے الیکٹرولائٹس ڈالیں'},
        ]

        for t_data in tasks_data:
            DailyTask.objects.get_or_create(name=t_data['name'], defaults=t_data)
        self.stdout.write(f'  Created {len(tasks_data)} daily tasks')

    def seed_articles(self):
        articles_data = [
            {
                'title': 'Common Poultry Diseases and Prevention',
                'title_ur': 'مرغیوں کی عام بیماریاں اور روک تھام',
                'category': 'disease',
                'content': 'Poultry diseases can cause significant losses. Common diseases include Newcastle Disease (ND), Infectious Bronchitis (IB), and Avian Influenza. Prevention starts with proper vaccination schedules, biosecurity measures, and maintaining clean water and feed.\n\n**Newcastle Disease:** Causes respiratory distress, nervous signs, and egg drop. Vaccinate at day 7 and booster at 3 weeks.\n\n**Gumboro (IBD):** Affects the immune system of young birds. Vaccinate at day 14.\n\n**Coccidiosis:** Caused by parasites in contaminated litter. Use anticoccidial medication in feed.',
                'content_ur': 'مرغیوں کی بیماریاں نمایاں نقصان کا سبب بن سکتی ہیں۔ عام بیماریوں میں نیوکیسل بیماری، انفیکشس برونکائٹس اور ایویئن انفلوئنزا شامل ہیں۔ روک تھام مناسب ویکسینیشن شیڈول، بائیو سیکیورٹی اور صاف پانی اور خوراک سے شروع ہوتی ہے۔',
            },
            {
                'title': 'Poultry Nutrition Guide',
                'title_ur': 'مرغیوں کی غذائیت گائیڈ',
                'category': 'nutrition',
                'content': 'Proper nutrition is essential for healthy poultry. Feed requirements vary by age:\n\n**Starter Feed (0-2 weeks):** High protein (22-24%) for rapid growth. Feed ad libitum.\n\n**Grower Feed (3-5 weeks):** Medium protein (20-22%). Transition gradually over 2-3 days.\n\n**Finisher Feed (6+ weeks):** Lower protein (18-20%) with higher energy for weight gain.\n\n**Layer Feed:** 16-18% protein with added calcium (3.5-4%) for eggshell production.\n\nAlways ensure clean, fresh water is available. Water consumption is typically 1.5-2x feed consumption.',
                'content_ur': 'مناسب غذائیت صحت مند مرغیوں کے لیے ضروری ہے۔ خوراک کی ضروریات عمر کے مطابق مختلف ہوتی ہیں۔',
            },
            {
                'title': 'Summer Heat Stress Management',
                'title_ur': 'گرمیوں میں ہیٹ اسٹریس کا انتظام',
                'category': 'seasonal',
                'content': 'Heat stress is a major concern during Pakistani summers when temperatures exceed 40°C.\n\n**Signs:** Panting, wings spread, reduced feed intake, drop in egg production.\n\n**Prevention:**\n- Provide cool, clean water at all times\n- Add electrolytes and vitamin C to water\n- Increase ventilation with fans and foggers\n- Reduce stocking density\n- Feed during cooler hours (early morning and evening)\n- Use white or reflective roofing\n- Plant trees around the shed for shade',
                'content_ur': 'پاکستان کی گرمیوں میں جب درجہ حرارت 40 ڈگری سے زیادہ ہو تو ہیٹ اسٹریس ایک بڑا مسئلہ ہے۔',
            },
            {
                'title': 'Winter Care for Poultry',
                'title_ur': 'سردیوں میں مرغیوں کی دیکھ بھال',
                'category': 'seasonal',
                'content': 'Cold weather requires special attention to keep your flock healthy and productive.\n\n**Heating:** Maintain shed temperature above 15°C for adults. Use heat lamps for chicks.\n\n**Ventilation:** Balance warmth with fresh air. Ammonia buildup is dangerous.\n\n**Lighting:** Provide 14-16 hours of light for layers to maintain egg production.\n\n**Feed:** Increase energy content by 5-10% in winter. Birds need extra calories to maintain body temperature.\n\n**Water:** Prevent water from freezing. Use warm water in extreme cold.',
                'content_ur': 'سرد موسم میں اپنے ریوڑ کو صحت مند اور پیداواری رکھنے کے لیے خصوصی توجہ درکار ہے۔',
            },
            {
                'title': 'Biosecurity Measures for Poultry Farms',
                'title_ur': 'پولٹری فارمز کے لیے بائیو سیکیورٹی',
                'category': 'health',
                'content': 'Biosecurity is the first line of defense against disease.\n\n**Key Measures:**\n- Restrict visitor access to the farm\n- Provide footbaths at entry points\n- Change clothes and shoes before entering sheds\n- Keep wild birds away from feed storage\n- Quarantine new birds for 2 weeks\n- Clean and disinfect between flocks\n- Dispose of dead birds properly\n- Keep records of all medications and vaccines',
                'content_ur': 'بائیو سیکیورٹی بیماری کے خلاف دفاع کی پہلی لائن ہے۔',
            },
            {
                'title': 'Egg Production Optimization',
                'title_ur': 'انڈوں کی پیداوار میں بہتری',
                'category': 'management',
                'content': 'Maximizing egg production requires attention to several factors:\n\n**Lighting:** 14-16 hours of light daily. Increase gradually, never decrease during lay.\n\n**Nutrition:** Layer feed with 3.5-4% calcium. Offer oyster shell separately.\n\n**Nesting:** Provide 1 nest box per 4-5 hens. Keep nests clean and dark.\n\n**Stress Reduction:** Minimize noise, handling, and environmental changes.\n\n**Record Keeping:** Track daily production to detect drops early.',
                'content_ur': 'انڈوں کی پیداوار کو زیادہ سے زیادہ کرنے کے لیے کئی عوامل پر توجہ دینی ہوگی۔',
            },
            {
                'title': 'Vaccination Schedule for Broilers',
                'title_ur': 'بروئلرز کے لیے ویکسینیشن شیڈول',
                'category': 'disease',
                'content': 'A proper vaccination schedule is critical for broiler health:\n\n| Day | Vaccine | Route |\n|-----|---------|-------|\n| 1 | Marek\'s Disease | Injection |\n| 7 | Newcastle (B1) + IB | Eye drop |\n| 14 | Gumboro (IBD) | Drinking water |\n| 21 | Newcastle (LaSota) | Drinking water |\n| 28 | Gumboro booster | Drinking water |\n\n**Tips:**\n- Use vaccine within 2 hours of mixing\n- Withhold water for 2 hours before water vaccination\n- Vaccinate in the cool morning hours',
                'content_ur': 'بروئلر کی صحت کے لیے مناسب ویکسینیشن شیڈول بہت ضروری ہے۔',
            },
            {
                'title': 'Farm Record Keeping Guide',
                'title_ur': 'فارم ریکارڈ رکھنے کی گائیڈ',
                'category': 'management',
                'content': 'Good record keeping helps you make informed decisions.\n\n**Daily Records:**\n- Feed consumption\n- Water consumption\n- Egg production (layers)\n- Mortality\n- Temperature (min/max)\n\n**Weekly Records:**\n- Body weight samples\n- Feed conversion ratio\n- Medication administered\n\n**Flock Records:**\n- Source and breed\n- Vaccination history\n- Total feed consumed\n- Final weight and sale price',
                'content_ur': 'اچھا ریکارڈ رکھنا آپ کو باخبر فیصلے کرنے میں مدد کرتا ہے۔',
            },
            {
                'title': 'Water Quality for Poultry',
                'title_ur': 'مرغیوں کے لیے پانی کا معیار',
                'category': 'health',
                'content': 'Water is the most important nutrient for poultry. Poor water quality leads to disease and reduced performance.\n\n**Quality Parameters:**\n- pH: 6.0-8.0\n- Total Dissolved Solids: <1000 ppm\n- Hardness: <110 ppm\n- Iron: <0.3 ppm\n\n**Best Practices:**\n- Test water regularly\n- Clean water lines between flocks\n- Use chlorination (2-5 ppm at drinker)\n- Flush lines daily in summer\n- Keep water tanks covered',
                'content_ur': 'پانی مرغیوں کے لیے سب سے اہم غذائی جزو ہے۔ خراب پانی کا معیار بیماری اور کم کارکردگی کا باعث بنتا ہے۔',
            },
            {
                'title': 'Starting a Small Poultry Farm',
                'title_ur': 'چھوٹا پولٹری فارم شروع کرنا',
                'category': 'management',
                'content': 'Starting a small poultry farm in Pakistan can be profitable with proper planning.\n\n**Initial Investment (100 birds):**\n- Shed construction: PKR 50,000-100,000\n- Day-old chicks: PKR 5,000-8,000\n- Feed for 6 weeks: PKR 30,000-40,000\n- Equipment: PKR 15,000-20,000\n- Vaccines: PKR 2,000-3,000\n\n**Tips:**\n- Start small and learn\n- Keep detailed financial records\n- Build relationships with reliable suppliers\n- Join local poultry farmer groups\n- Focus on biosecurity from day one',
                'content_ur': 'مناسب منصوبہ بندی کے ساتھ پاکستان میں چھوٹا پولٹری فارم شروع کرنا منافع بخش ہو سکتا ہے۔',
            },
        ]

        for a_data in articles_data:
            Article.objects.get_or_create(title=a_data['title'], defaults=a_data)
        self.stdout.write(f'  Created {len(articles_data)} articles')
