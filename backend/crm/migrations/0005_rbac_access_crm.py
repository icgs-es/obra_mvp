from django.db import migrations


CODENAME = "access_crm"
NAME = "Puede acceder al módulo CRM"

AUTHORIZED_GROUPS = (
    "Gerencia",
    "Comercializadora",
)


def create_permission(apps, schema_editor):
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
        app_label="crm",
        model="lead",
    )

    permission, _ = (
        Permission.objects.update_or_create(
            content_type=content_type,
            codename=CODENAME,
            defaults={
                "name": NAME,
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


def remove_permission(apps, schema_editor):
    Permission = apps.get_model(
        "auth",
        "Permission",
    )

    Permission.objects.filter(
        content_type__app_label="crm",
        codename=CODENAME,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "crm",
            "0004_lead_activo_lead",
        ),
    ]

    operations = [
        migrations.RunPython(
            create_permission,
            remove_permission,
        ),
    ]
