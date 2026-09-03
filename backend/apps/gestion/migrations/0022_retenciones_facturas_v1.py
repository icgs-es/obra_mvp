from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0021_factura_vencimientos_abono_negativos")]

    operations = [
        migrations.AddField(
            model_name="proveedor",
            name="aplica_retencion_habitual",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="proveedor",
            name="retencion_habitual_porcentaje",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="facturaproveedorgestion",
            name="retencion_porcentaje",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
    ]
