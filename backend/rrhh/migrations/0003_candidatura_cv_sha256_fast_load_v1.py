import hashlib

from django.db import migrations, models


def _digest_file(file_field):
    if not file_field:
        return ""

    digest = hashlib.sha256()

    try:
        file_field.open("rb")
        for chunk in iter(
            lambda: file_field.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
        return digest.hexdigest()
    except (FileNotFoundError, OSError, ValueError):
        return ""
    finally:
        try:
            file_field.close()
        except Exception:
            pass


def backfill_cv_sha256(apps, schema_editor):
    Candidatura = apps.get_model("rrhh", "Candidatura")

    for application in (
        Candidatura.objects
        .exclude(cv_fichero="")
        .iterator(chunk_size=100)
    ):
        digest = _digest_file(application.cv_fichero)
        if digest:
            Candidatura.objects.filter(
                pk=application.pk
            ).update(cv_sha256=digest)


class Migration(migrations.Migration):
    dependencies = [
        ("rrhh", "0002_seleccion_personal_v1"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidatura",
            name="cv_sha256",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=64,
            ),
        ),
        migrations.RunPython(
            backfill_cv_sha256,
            migrations.RunPython.noop,
        ),
    ]
