from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_farm_fcm_token_mortalitylog_treatmentrecord_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='expert',
            name='about',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='expert',
            name='city',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='expert',
            name='clinic_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='consultation_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='expert',
            name='consultation_hours',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='languages',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='qualification',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='rating',
            field=models.DecimalField(decimal_places=2, default=4.5, max_digits=3),
        ),
        migrations.AddField(
            model_name='expert',
            name='total_consultations',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='expert',
            name='years_experience',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
