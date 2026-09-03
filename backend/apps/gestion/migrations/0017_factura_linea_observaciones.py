from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "gestion",
            "0016_rbac_access_gestion",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="facturaproveedorlineagestion",
            name="observaciones",
            field=models.TextField(
                blank=True,
                default="",
            ),
            preserve_default=False,
        ),
    ]
