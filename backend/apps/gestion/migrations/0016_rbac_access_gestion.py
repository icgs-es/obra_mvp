from django.db import migrations


PERMISSION_CODENAME = "access_gestion"
PERMISSION_NAME = "Puede acceder al módulo Gestión"

AUTHORIZED_GROUPS = (
    "Administracion",
    "Gerencia",
)


def create_access_permission(apps, schema_editor):
    ContentType = apps.get_model(
        "contenttypes",
        "ContentType",
    )

    Permission = apps.get_model(
        "auth",
        "Permission",
    )

    Group = apps.get_model(
        "auth",
        "Group",
    )

    content_type, _ = ContentType.objects.get_or_create(
        app_label="gestion",
        model="proveedor",
    )

    permission, _ = (
        Permission.objects.update_or_create(
            content_type=content_type,
            codename=PERMISSION_CODENAME,
            defaults={
                "name": PERMISSION_NAME,
            },
        )
    )

    groups = []

    for group_name in AUTHORIZED_GROUPS:
        group, _ = Group.objects.get_or_create(
            name=group_name
        )
        groups.append(group)

    for group in groups:
        group.permissions.add(permission)


def remove_access_permission(apps, schema_editor):
    Permission = apps.get_model(
        "auth",
        "Permission",
    )

    Permission.objects.filter(
        content_type__app_label="gestion",
        codename=PERMISSION_CODENAME,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "gestion",
            "0015_factura_linea_unidad_compra",
        ),
    ]

    operations = [
        migrations.RunPython(
            create_access_permission,
            remove_access_permission,
        ),
    ]
