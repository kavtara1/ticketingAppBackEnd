from django.db import migrations, models


def populate_telephonegram_ids(apps, schema_editor):
    Telephonegram = apps.get_model("ticketing", "Telephonegram")
    for telephonegram in Telephonegram.objects.filter(telephonegram_id__isnull=True).iterator():
        telephonegram.telephonegram_id = telephonegram.id
        telephonegram.save(update_fields=["telephonegram_id"])


def clear_telephonegram_ids(apps, schema_editor):
    Telephonegram = apps.get_model("ticketing", "Telephonegram")
    Telephonegram.objects.update(telephonegram_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0009_alter_ticket_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="telephonegram",
            name="telephonegram_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(populate_telephonegram_ids, clear_telephonegram_ids),
        migrations.AlterField(
            model_name="telephonegram",
            name="telephonegram_id",
            field=models.PositiveIntegerField(unique=True),
        ),
    ]
