from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_chatroom_firestore_room_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketRateOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region_key', models.CharField(
                    choices=[
                        ('lahore', 'Lahore'),
                        ('karachi', 'Karachi'),
                        ('islamabad', 'Islamabad'),
                        ('rawalpindi', 'Rawalpindi'),
                        ('faisalabad', 'Faisalabad'),
                        ('multan', 'Multan'),
                        ('peshawar', 'Peshawar'),
                        ('quetta', 'Quetta'),
                    ],
                    db_index=True, max_length=32,
                )),
                ('date', models.CharField(db_index=True, help_text='YYYY-MM-DD', max_length=10)),
                ('egg_tray_price', models.PositiveIntegerField(help_text='PKR per 30 eggs')),
                ('broiler_live_per_kg', models.PositiveIntegerField(help_text='PKR per kg live')),
                ('doc_price', models.PositiveIntegerField(blank=True, help_text='PKR per day-old chick', null=True)),
                ('feed_starter_per_bag', models.PositiveIntegerField(blank=True, help_text='PKR per 50 kg bag', null=True)),
                ('feed_grower_per_bag', models.PositiveIntegerField(blank=True, null=True)),
                ('feed_finisher_per_bag', models.PositiveIntegerField(blank=True, null=True)),
                ('note', models.CharField(blank=True, default='', max_length=255)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-date', 'region_key'],
                'unique_together': {('region_key', 'date')},
            },
        ),
    ]
