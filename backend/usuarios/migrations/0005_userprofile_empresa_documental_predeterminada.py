import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "usuarios",
            "0004_alter_userprofile_color",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name=(
                "empresa_documental_predeterminada"
            ),
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Empresa utilizada para documentos "
                    "cuando el selector global está en "
                    "Todas sus empresas."
                ),
                null=True,
                on_delete=(
                    django.db.models.deletion.SET_NULL
                ),
                related_name=(
                    "perfiles_documentales_predeterminados"
                ),
                to="usuarios.team",
            ),
        ),
    ]
