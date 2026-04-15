from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_expert_profile_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagnosisresult',
            name='all_probabilities',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
