from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0014_proveedor_ambito_gestion_v1"),
    ]

    operations = [
        migrations.AddField(
            model_name="facturaproveedorlineagestion",
            name="unidad_compra",
            field=models.CharField(
                blank=True,
                max_length=30,
            ),
        ),
    ]
