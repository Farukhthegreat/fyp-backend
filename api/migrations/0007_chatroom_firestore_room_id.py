from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_diagnosisresult_all_probabilities'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE api_chatroom "
                        "ADD COLUMN IF NOT EXISTS firestore_room_id "
                        "VARCHAR(255) NOT NULL DEFAULT ''"
                    ),
                    reverse_sql=(
                        "ALTER TABLE api_chatroom "
                        "DROP COLUMN IF EXISTS firestore_room_id"
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='chatroom',
                    name='firestore_room_id',
                    field=models.CharField(
                        blank=True,
                        default='',
                        help_text='Firestore document ID for this room',
                        max_length=255,
                    ),
                ),
            ],
        ),
    ]
