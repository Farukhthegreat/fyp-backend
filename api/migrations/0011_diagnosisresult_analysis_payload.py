from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_remove_marketrateoverride_doc_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagnosisresult',
            name='analysis_payload',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
