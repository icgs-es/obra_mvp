from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


AUTHORIZE_PERMISSION = (
    "authorize_factura_payment_plan"
)

REGISTER_PERMISSION = (
    "register_factura_installment_payment"
)


def create_payment_permissions(
    apps,
    schema_editor,
):
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

    content_type, _ = (
        ContentType.objects.get_or_create(
            app_label="gestion",
            model="facturavencimientogestion",
        )
    )

    authorize_permission, _ = (
        Permission.objects.update_or_create(
            content_type=content_type,
            codename=AUTHORIZE_PERMISSION,
            defaults={
                "name": (
                    "Puede autorizar planes "
                    "de pago de facturas"
                ),
            },
        )
    )

    register_permission, _ = (
        Permission.objects.update_or_create(
            content_type=content_type,
            codename=REGISTER_PERMISSION,
            defaults={
                "name": (
                    "Puede registrar pagos "
                    "de vencimientos"
                ),
            },
        )
    )

    gerencia, _ = Group.objects.get_or_create(
        name="Gerencia"
    )
    administracion, _ = (
        Group.objects.get_or_create(
            name="Administracion"
        )
    )

    gerencia.permissions.add(
        authorize_permission
    )

    administracion.permissions.add(
        register_permission
    )


def remove_payment_permissions(
    apps,
    schema_editor,
):
    Permission = apps.get_model(
        "auth",
        "Permission",
    )

    Permission.objects.filter(
        content_type__app_label="gestion",
        content_type__model=(
            "facturavencimientogestion"
        ),
        codename__in=[
            AUTHORIZE_PERMISSION,
            REGISTER_PERMISSION,
        ],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "gestion",
            "0017_factura_linea_observaciones",
        ),
        migrations.swappable_dependency(
            settings.AUTH_USER_MODEL
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="FacturaVencimientoGestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "numero_pago",
                    models.PositiveIntegerField(),
                ),
                (
                    "fecha_vencimiento",
                    models.DateField(),
                ),
                (
                    "importe_previsto",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            (
                                "PENDIENTE",
                                "Pendiente",
                            ),
                            (
                                "PAGADO",
                                "Pagado",
                            ),
                            (
                                "ANULADO",
                                "Anulado",
                            ),
                        ],
                        default="PENDIENTE",
                        max_length=20,
                    ),
                ),
                (
                    "fecha_real_pago",
                    models.DateField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "importe_pagado",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                    ),
                ),
                (
                    "forma_pago",
                    models.CharField(
                        blank=True,
                        max_length=160,
                    ),
                ),
                (
                    "referencia_pago",
                    models.CharField(
                        blank=True,
                        max_length=255,
                    ),
                ),
                (
                    "observaciones",
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "autorizado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=(
                            django.db.models
                            .deletion.SET_NULL
                        ),
                        related_name=(
                            "gestion_vencimientos_"
                            "autorizados"
                        ),
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "factura",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models
                            .deletion.CASCADE
                        ),
                        related_name=(
                            "vencimientos_pago"
                        ),
                        to=(
                            "gestion."
                            "facturaproveedorgestion"
                        ),
                    ),
                ),
                (
                    "pagado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=(
                            django.db.models
                            .deletion.SET_NULL
                        ),
                        related_name=(
                            "gestion_vencimientos_"
                            "pagados"
                        ),
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models
                            .deletion.PROTECT
                        ),
                        related_name=(
                            "gestion_factura_"
                            "vencimientos"
                        ),
                        to="usuarios.team",
                    ),
                ),
            ],
            options={
                "verbose_name": (
                    "Vencimiento de factura"
                ),
                "verbose_name_plural": (
                    "Vencimientos de facturas"
                ),
                "ordering": [
                    "fecha_vencimiento",
                    "numero_pago",
                ],
                "permissions": [
                    (
                        AUTHORIZE_PERMISSION,
                        "Puede autorizar planes "
                        "de pago de facturas",
                    ),
                    (
                        REGISTER_PERMISSION,
                        "Puede registrar pagos "
                        "de vencimientos",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=[
                            "team",
                            "fecha_vencimiento",
                        ],
                        name=(
                            "gestion_venc_team_"
                            "fecha_idx"
                        ),
                    ),
                    models.Index(
                        fields=[
                            "factura",
                            "estado",
                        ],
                        name=(
                            "gestion_venc_fact_"
                            "est_idx"
                        ),
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "factura",
                            "numero_pago",
                        ),
                        name=(
                            "uniq_gestion_factura_"
                            "venc_num"
                        ),
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            importe_previsto__gt=0
                        ),
                        name=(
                            "chk_gestion_venc_"
                            "importe_pos"
                        ),
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            importe_pagado__gte=0
                        ),
                        name=(
                            "chk_gestion_venc_"
                            "pagado_nonneg"
                        ),
                    ),
                ],
            },
        ),
        migrations.RunPython(
            create_payment_permissions,
            remove_payment_permissions,
        ),
    ]
