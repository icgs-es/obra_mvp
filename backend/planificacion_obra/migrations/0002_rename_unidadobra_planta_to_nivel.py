from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("planificacion_obra", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="unidadobra",
            old_name="planta",
            new_name="nivel",
        ),
    ]
