from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_expert_profile_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE api_diagnosisresult "
                        "ADD COLUMN IF NOT EXISTS all_probabilities JSONB NULL"
                    ),
                    reverse_sql=(
                        "ALTER TABLE api_diagnosisresult "
                        "DROP COLUMN IF EXISTS all_probabilities"
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='diagnosisresult',
                    name='all_probabilities',
                    field=models.JSONField(blank=True, null=True),
                ),
            ],
        ),
    ]
