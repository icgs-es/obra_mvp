from django.db import (
    migrations,
    models,
)


class Migration(
    migrations.Migration,
):

    dependencies = [
        (
            "gestion",
            "0019_factura_planes_legacy_v1",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="facturaproveedorgestion",
            name="tipo_factura",
            field=models.CharField(
                choices=[
                    (
                        "NORMAL",
                        "Normal",
                    ),
                    (
                        "RECTIFICATIVA",
                        "Rectificativa",
                    ),
                ],
                db_index=True,
                default="NORMAL",
                max_length=20,
            ),
        ),

        migrations.AddField(
            model_name="facturaproveedorgestion",
            name="subtipo_rectificativa",
            field=models.CharField(
                blank=True,
                choices=[
                    (
                        "",
                        "—",
                    ),
                    (
                        "ABONO",
                        "Abono",
                    ),
                    (
                        "OTRA",
                        "Otra rectificativa",
                    ),
                ],
                default="",
                max_length=20,
            ),
        ),

        migrations.AddField(
            model_name="facturaproveedorgestion",
            name="numero_factura_rectificada",
            field=models.CharField(
                blank=True,
                default="",
                max_length=120,
            ),
        ),

        migrations.AddField(
            model_name="facturaproveedorgestion",
            name="factura_rectificada",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="documentos_rectificativos",
                to="gestion.facturaproveedorgestion",
            ),
        ),
    ]
