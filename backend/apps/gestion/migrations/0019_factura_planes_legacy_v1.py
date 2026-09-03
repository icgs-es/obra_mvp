from datetime import date
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


MARKER = "[LEGACY_BACKFILL_V1]"
SNAPSHOT_KEY = (
    "_factura_pagos_multiples_v1_snapshot"
)


def date_value(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def forwards(apps, schema_editor):
    Factura = apps.get_model(
        "gestion",
        "FacturaProveedorGestion",
    )
    Vencimiento = apps.get_model(
        "gestion",
        "FacturaVencimientoGestion",
    )

    queryset = (
        Factura.objects
        .filter(
            importe_factura__gt=0,
            importe_pagado__gte=0,
        )
        .exclude(estado="ANULADA")
        .order_by("id")
    )

    for factura in queryset.iterator(
        chunk_size=200
    ):
        if Vencimiento.objects.filter(
            factura_id=factura.id
        ).exists():
            continue

        total = Decimal(
            factura.importe_factura or 0
        )

        pagado_legacy = Decimal(
            factura.importe_pagado or 0
        )

        if total <= 0 or pagado_legacy < 0:
            continue

        estado_original = (
            factura.estado or ""
        ).strip().upper()

        fecha_origen = "CONTRATO"

        fecha_vencimiento = (
            factura.fecha_pago_segun_contrato
        )

        if not fecha_vencimiento:
            fecha_vencimiento = (
                factura.fecha_emision
            )
            fecha_origen = "EMISION"

        if not fecha_vencimiento:
            fecha_vencimiento = (
                factura.created_at.date()
                if factura.created_at
                else timezone.localdate()
            )
            fecha_origen = "ALTA_SISTEMA"

        pagada = estado_original == "PAGADA"

        autorizada = bool(
            factura.fecha_autorizacion_gerencia
        ) and not pagada

        raw_data = dict(
            factura.raw_data or {}
        )

        if SNAPSHOT_KEY not in raw_data:
            raw_data[SNAPSHOT_KEY] = {
                "estado": factura.estado or "",
                "fecha_autorizacion_gerencia": (
                    factura
                    .fecha_autorizacion_gerencia
                    .isoformat()
                    if factura
                    .fecha_autorizacion_gerencia
                    else None
                ),
                "fecha_pago_segun_contrato": (
                    factura
                    .fecha_pago_segun_contrato
                    .isoformat()
                    if factura
                    .fecha_pago_segun_contrato
                    else None
                ),
                "fecha_real_pago": (
                    factura
                    .fecha_real_pago
                    .isoformat()
                    if factura.fecha_real_pago
                    else None
                ),
                "importe_pagado": str(
                    factura.importe_pagado or 0
                ),
            }

        Vencimiento.objects.create(
            team_id=factura.team_id,
            factura_id=factura.id,
            numero_pago=1,
            fecha_vencimiento=(
                fecha_vencimiento
            ),
            importe_previsto=total,
            estado=(
                "PAGADO"
                if pagada
                else "PENDIENTE"
            ),
            fecha_real_pago=(
                factura.fecha_real_pago
                if pagada
                else None
            ),
            importe_pagado=(
                total
                if pagada
                else Decimal("0.00")
            ),
            forma_pago=(
                factura.forma_pago or ""
            ),
            referencia_pago="",
            observaciones=(
                f"{MARKER} "
                "Plan único generado desde datos "
                f"históricos. Fecha={fecha_origen}."
            ),
            autorizado_por_id=None,
            pagado_por_id=None,
        )

        factura.raw_data = raw_data
        factura.fecha_pago_segun_contrato = (
            fecha_vencimiento
        )

        update_fields = [
            "raw_data",
            "fecha_pago_segun_contrato",
        ]

        if pagada:
            factura.importe_pagado = total
            update_fields.append(
                "importe_pagado"
            )

        elif autorizada:
            factura.estado = "AUT. PAGO"
            update_fields.append("estado")

        factura.save(
            update_fields=update_fields
        )



def backwards(apps, schema_editor):
    Factura = apps.get_model(
        "gestion",
        "FacturaProveedorGestion",
    )
    Vencimiento = apps.get_model(
        "gestion",
        "FacturaVencimientoGestion",
    )

    invoices = Factura.objects.order_by("id")

    for factura in invoices.iterator(
        chunk_size=200
    ):
        # FIX1_ROLLBACK_ONLY_LEGACY_BACKFILL
        legacy_vencimientos = (
            Vencimiento.objects.filter(
                factura_id=factura.id,
                observaciones__startswith=MARKER,
            )
        )

        if not legacy_vencimientos.exists():
            continue

        raw_data = dict(
            factura.raw_data or {}
        )

        snapshot = raw_data.pop(
            SNAPSHOT_KEY,
            None,
        )

        legacy_vencimientos.delete()

        if not snapshot:
            continue

        factura.estado = (
            snapshot.get("estado") or ""
        )

        factura.fecha_autorizacion_gerencia = (
            date_value(
                snapshot.get(
                    "fecha_autorizacion_gerencia"
                )
            )
        )

        factura.fecha_pago_segun_contrato = (
            date_value(
                snapshot.get(
                    "fecha_pago_segun_contrato"
                )
            )
        )

        factura.fecha_real_pago = date_value(
            snapshot.get("fecha_real_pago")
        )

        factura.importe_pagado = Decimal(
            snapshot.get("importe_pagado")
            or "0"
        )

        factura.raw_data = raw_data

        factura.save(
            update_fields=[
                "estado",
                "fecha_autorizacion_gerencia",
                "fecha_pago_segun_contrato",
                "fecha_real_pago",
                "importe_pagado",
                "raw_data",
            ]
        )

class Migration(migrations.Migration):

    dependencies = [
        (
            "gestion",
            "0018_factura_pagos_multiples_v1",
        ),
    ]

    operations = [
        migrations.RunPython(
            forwards,
            backwards,
        ),
    ]
