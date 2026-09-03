from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "archivos",
            "0007_archivo_team_carpeta_team",
        ),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="archivo",
            options={
                "ordering": [
                    "-created_at",
                ],
                "permissions": [
                    (
                        "upload_folder",
                        (
                            "Puede subir carpetas "
                            "completas en INTASA Cloud"
                        ),
                    ),
                ],
                "verbose_name": "archivo",
                "verbose_name_plural": (
                    "archivos"
                ),
            },
        ),
    ]
