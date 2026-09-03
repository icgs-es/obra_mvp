from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_fuentelead_activo_interes_text"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="fuente",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leads",
                to="crm.fuentelead",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="activo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leads",
                to="crm.activo",
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="tipo_activo",
            field=models.CharField(
                max_length=24,
                blank=True,
                choices=[
                    ("mensaje", "Mensaje"),
                    ("llamada", "Llamada"),
                ],
            ),
        ),
    ]