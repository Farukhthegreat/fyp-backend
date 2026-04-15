from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_diagnosisresult_all_probabilities'),
    ]

    operations = [
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
    ]
