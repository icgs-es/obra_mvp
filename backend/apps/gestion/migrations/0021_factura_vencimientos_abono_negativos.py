from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion", "0020_factura_rectificativa_v1")]

    operations = [
        migrations.RemoveConstraint(model_name="facturavencimientogestion", name="chk_gestion_venc_importe_pos"),
        migrations.RemoveConstraint(model_name="facturavencimientogestion", name="chk_gestion_venc_pagado_nonneg"),
        migrations.AddConstraint(
            model_name="facturavencimientogestion",
            constraint=models.CheckConstraint(
                check=models.Q(importe_previsto__gt=0) | models.Q(importe_previsto__lt=0),
                name="chk_gestion_venc_importe_pos",
            ),
        ),
        migrations.AddConstraint(
            model_name="facturavencimientogestion",
            constraint=models.CheckConstraint(
                check=models.Q(importe_pagado__gte=0) | models.Q(importe_pagado__lt=0),
                name="chk_gestion_venc_pagado_nonneg",
            ),
        ),
    ]
