from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "planificacion_obra",
            "0008_alter_asignacionobra_options_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="asignacionobra",
            name="cantidad_ejecutada",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="asignacionobra",
            name="unidad_ejecutada",
            field=models.CharField(
                blank=True,
                max_length=40,
            ),
        ),
    ]
