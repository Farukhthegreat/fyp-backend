from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_expert_urdu_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='is_auto_generated',
            field=models.BooleanField(default=False),
        ),
    ]
