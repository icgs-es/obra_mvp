from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0022_retenciones_facturas_v1")]

    operations = [
        migrations.AlterModelOptions(
            name="proveedor",
            options={
                "ordering": ["nombre_comercial"],
                "permissions": [
                    ("manage_supplier_retention_settings", "Puede configurar la retención habitual de proveedores"),
                ],
                "verbose_name": "Proveedor",
                "verbose_name_plural": "Proveedores",
            },
        ),
        migrations.AlterModelOptions(
            name="facturaproveedorgestion",
            options={
                "ordering": ["-fecha_emision", "-cod_factura"],
                "permissions": [
                    ("edit_invoice_withholding", "Puede editar retenciones de facturas de proveedor"),
                ],
                "verbose_name": "Factura de proveedor",
                "verbose_name_plural": "Facturas de proveedores",
            },
        ),
        migrations.AlterField(
            model_name="proveedor",
            name="aplica_retencion_habitual",
            field=models.BooleanField(
                default=False,
                help_text="Propone la retención al crear facturas de este proveedor en este equipo.",
            ),
        ),
        migrations.AlterField(
            model_name="proveedor",
            name="retencion_habitual_porcentaje",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Porcentaje propuesto; la factura y el PDF pueden establecer otro.",
                max_digits=6,
            ),
        ),
    ]
