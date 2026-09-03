from django.db import migrations


GROUPS = ("Administracion", "Gerencia")
PERMISSIONS = (
    "edit_invoice_withholding",
    "manage_supplier_retention_settings",
)


def assign_operational_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = list(Permission.objects.filter(
        content_type__app_label="gestion",
        codename__in=PERMISSIONS,
    ))
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.add(*permissions)


def remove_operational_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = list(Permission.objects.filter(
        content_type__app_label="gestion",
        codename__in=PERMISSIONS,
    ))
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [("gestion", "0023_retenciones_permissions_v1")]
    operations = [migrations.RunPython(assign_operational_permissions, remove_operational_permissions)]
