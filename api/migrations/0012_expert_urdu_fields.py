from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_diagnosisresult_analysis_payload'),
    ]

    operations = [
        migrations.AddField(
            model_name='expert',
            name='specialization_urdu',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='qualification_urdu',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='clinic_name_urdu',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='city_urdu',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='expert',
            name='consultation_hours_urdu',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='expert',
            name='about_urdu',
            field=models.TextField(blank=True, default=''),
        ),
    ]
