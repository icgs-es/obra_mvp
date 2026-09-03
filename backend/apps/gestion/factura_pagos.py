# FACTURA_PAGOS_MULTIPLES_V1
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Min, Sum
from django.utils import timezone

from apps.gestion.models import (
    FacturaProveedorGestion,
    FacturaVencimientoGestion,
)


CENT = Decimal("0.01")
SNAPSHOT_KEY = "_factura_pagos_multiples_v1_snapshot"


def money(value):
    return (
        Decimal(str(value or "0"))
        .quantize(CENT, rounding=ROUND_HALF_UP)
    )


def validar_plan_pago(
    importe_factura,
    lineas,
):
    total_factura = money(importe_factura)

    if total_factura == 0:
        raise ValidationError(
            "No se puede autorizar un plan para una "
            "factura con importe cero."
        )

    es_abono = total_factura < 0

    normalizadas = []

    for index, linea in enumerate(
        lineas,
        start=1,
    ):
        fecha_vencimiento = linea.get(
            "fecha_vencimiento"
        )
        importe_previsto = money(
            linea.get("importe_previsto")
        )
        forma_pago = (
            linea.get("forma_pago") or ""
        ).strip()

        if not fecha_vencimiento:
            raise ValidationError(
                f"El pago {index} no tiene fecha."
            )

        if not es_abono and importe_previsto <= 0:
            raise ValidationError(
                f"El pago {index} debe tener "
                "un importe superior a cero."
            )

        if es_abono and importe_previsto >= 0:
            raise ValidationError(
                f"La devolución {index} debe tener "
                "un importe negativo."
            )

        if es_abono and not (
            forma_pago.upper().startswith("TRANSFERENCIA")
            or forma_pago.upper().startswith("DEVOLUCION")
            or forma_pago.upper().startswith("DEVOLUCIÓN")
        ):
            raise ValidationError(
                f"La devolución {index} debe usar "
                "Transferencia o Devolución como forma de pago."
            )

        normalizadas.append({
            "numero_pago": index,
            "fecha_vencimiento": fecha_vencimiento,
            "importe_previsto": importe_previsto,
            "forma_pago": forma_pago,
            "observaciones": (
                linea.get("observaciones") or ""
            ).strip(),
        })

    if not normalizadas:
        raise ValidationError(
            "Debe existir al menos un vencimiento."
        )

    total_plan = sum(
        (
            item["importe_previsto"]
            for item in normalizadas
        ),
        Decimal("0.00"),
    ).quantize(CENT)

    if total_plan != total_factura:
        raise ValidationError(
            "La suma de los vencimientos "
            f"({total_plan:.2f} €) debe coincidir "
            f"con el total de la factura "
            f"({total_factura:.2f} €)."
        )

    return normalizadas


def _scope_factura(
    factura_id,
    team_ids=None,
):
    queryset = (
        FacturaProveedorGestion.objects
        .select_for_update()
    )

    if team_ids is not None:
        queryset = queryset.filter(
            team_id__in=list(team_ids)
        )

    return queryset.get(pk=factura_id)


def _snapshot_legacy(factura):
    raw_data = dict(
        factura.raw_data or {}
    )

    if SNAPSHOT_KEY not in raw_data:
        raw_data[SNAPSHOT_KEY] = {
            "estado": factura.estado or "",
            "fecha_autorizacion_gerencia": (
                factura.fecha_autorizacion_gerencia.isoformat()
                if factura.fecha_autorizacion_gerencia
                else None
            ),
            "fecha_pago_segun_contrato": (
                factura.fecha_pago_segun_contrato.isoformat()
                if factura.fecha_pago_segun_contrato
                else None
            ),
            "fecha_real_pago": (
                factura.fecha_real_pago.isoformat()
                if factura.fecha_real_pago
                else None
            ),
            "importe_pagado": str(
                factura.importe_pagado
                or Decimal("0.00")
            ),
        }

    factura.raw_data = raw_data


def _parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def recalcular_factura_desde_vencimientos(
    factura,
):
    vencimientos = list(
        factura.vencimientos_pago
        .select_for_update()
        .order_by(
            "fecha_vencimiento",
            "numero_pago",
        )
    )

    if not vencimientos:
        return factura

    pagados = [
        item
        for item in vencimientos
        if item.estado
        == FacturaVencimientoGestion.ESTADO_PAGADO
    ]

    pendientes = [
        item
        for item in vencimientos
        if item.estado
        == FacturaVencimientoGestion.ESTADO_PENDIENTE
    ]

    total_pagado = sum(
        (
            money(item.importe_pagado)
            for item in pagados
        ),
        Decimal("0.00"),
    ).quantize(CENT)

    total_factura = money(
        factura.importe_factura
    )

    if total_factura < 0:
        if not pagados:
            estado = "AUT. PAGO"
        elif not pendientes and total_pagado == total_factura:
            estado = "PAGADA"
        else:
            estado = "PARCIAL"
    elif total_pagado <= 0:
        estado = "AUT. PAGO"
    elif not pendientes and total_pagado >= total_factura:
        estado = "PAGADA"
    else:
        estado = "PARCIAL"

    siguiente_vencimiento = (
        min(
            (
                item.fecha_vencimiento
                for item in pendientes
            ),
            default=None,
        )
    )

    ultima_fecha_pago = max(
        (
            item.fecha_real_pago
            for item in pagados
            if item.fecha_real_pago
        ),
        default=None,
    )

    if not siguiente_vencimiento:
        siguiente_vencimiento = max(
            (
                item.fecha_vencimiento
                for item in vencimientos
            ),
            default=None,
        )

    factura.estado = estado
    factura.importe_pagado = total_pagado
    factura.fecha_pago_segun_contrato = (
        siguiente_vencimiento
    )
    factura.fecha_real_pago = ultima_fecha_pago

    factura.save(update_fields=[
        "estado",
        "importe_pagado",
        "fecha_pago_segun_contrato",
        "fecha_real_pago",
        "updated_at",
    ])

    return factura


@transaction.atomic
def autorizar_plan_pago(
    *,
    factura_id,
    user,
    lineas,
    team_ids=None,
):
    factura = _scope_factura(
        factura_id,
        team_ids,
    )

    # FACTURA_PLAN_INTEGRIDAD_CANONICA_V2: no se autorizan pagos/devoluciones
    # mientras la cabecera no coincida con sus líneas firmadas.
    from apps.gestion.views import gestion_factura_validar_integridad_canonica_v2
    gestion_factura_validar_integridad_canonica_v2(factura)

    if (factura.estado or "").upper() in {
        "PAGADA",
        "ANULADA",
    }:
        raise ValidationError(
            "No se puede autorizar un plan "
            f"para una factura {factura.estado}."
        )

    existentes = list(
        factura.vencimientos_pago
        .select_for_update()
        .all()
    )

    if any(
        item.estado
        == FacturaVencimientoGestion.ESTADO_PAGADO
        for item in existentes
    ):
        raise ValidationError(
            "El plan no puede modificarse porque "
            "ya contiene pagos realizados."
        )

    if (
        not existentes
        and money(factura.importe_pagado) != 0
    ):
        raise ValidationError(
            "La factura ya contiene un importe "
            "pagado histórico. Debe revisarse antes "
            "de crear un plan nuevo."
        )

    lineas = validar_plan_pago(
        factura.importe_factura,
        lineas,
    )

    _snapshot_legacy(factura)

    factura.vencimientos_pago.all().delete()

    FacturaVencimientoGestion.objects.bulk_create([
        FacturaVencimientoGestion(
            team=factura.team,
            factura=factura,
            numero_pago=item["numero_pago"],
            fecha_vencimiento=item[
                "fecha_vencimiento"
            ],
            importe_previsto=item[
                "importe_previsto"
            ],
            importe_pagado=Decimal("0.00"),
            estado=(
                FacturaVencimientoGestion
                .ESTADO_PENDIENTE
            ),
            forma_pago=item["forma_pago"],
            observaciones=item["observaciones"],
            autorizado_por=user,
        )
        for item in lineas
    ])

    factura.fecha_autorizacion_gerencia = (
        timezone.localdate()
    )
    factura.estado = "AUT. PAGO"
    factura.importe_pagado = Decimal("0.00")
    factura.fecha_real_pago = None
    factura.fecha_pago_segun_contrato = min(
        item["fecha_vencimiento"]
        for item in lineas
    )
    factura.modificado_por = user
    factura.save(update_fields=[
        "fecha_autorizacion_gerencia",
        "estado",
        "importe_pagado",
        "fecha_real_pago",
        "fecha_pago_segun_contrato",
        "modificado_por",
        "raw_data",
        "updated_at",
    ])

    return factura


@transaction.atomic
def registrar_pago_vencimiento(
    *,
    vencimiento_id,
    user,
    fecha_real_pago=None,
    referencia_pago="",
    team_ids=None,
):
    queryset = (
        FacturaVencimientoGestion.objects
        .select_for_update()
        .select_related("factura")
    )

    if team_ids is not None:
        queryset = queryset.filter(
            team_id__in=list(team_ids)
        )

    vencimiento = queryset.get(
        pk=vencimiento_id
    )

    factura = _scope_factura(
        vencimiento.factura_id,
        team_ids,
    )

    # FACTURA_PLAN_AUTHORIZATION_GUARD_V1B
    estado_factura = (
        factura.estado or ""
    ).strip().upper()

    if (
        not factura.fecha_autorizacion_gerencia
        or estado_factura not in {
            "AUT. PAGO",
            "PARCIAL",
        }
    ):
        raise ValidationError(
            "Gerencia debe autorizar el plan "
            "antes de registrar pagos."
        )

    if vencimiento.estado == (
        FacturaVencimientoGestion
        .ESTADO_PAGADO
    ):
        return factura

    if vencimiento.estado != (
        FacturaVencimientoGestion
        .ESTADO_PENDIENTE
    ):
        raise ValidationError(
            "El vencimiento no está pendiente."
        )

    vencimiento.estado = (
        FacturaVencimientoGestion
        .ESTADO_PAGADO
    )
    vencimiento.fecha_real_pago = (
        fecha_real_pago
        or timezone.localdate()
    )
    vencimiento.importe_pagado = (
        vencimiento.importe_previsto
    )
    vencimiento.referencia_pago = (
        referencia_pago or ""
    ).strip()
    vencimiento.pagado_por = user

    if not vencimiento.forma_pago:
        vencimiento.forma_pago = (
            factura.forma_pago or ""
        )

    vencimiento.save(update_fields=[
        "estado",
        "fecha_real_pago",
        "importe_pagado",
        "referencia_pago",
        "pagado_por",
        "forma_pago",
        "updated_at",
    ])

    return recalcular_factura_desde_vencimientos(
        factura
    )


@transaction.atomic
def eliminar_plan_pago(
    *,
    factura_id,
    user,
    team_ids=None,
):
    factura = _scope_factura(
        factura_id,
        team_ids,
    )

    vencimientos = list(
        factura.vencimientos_pago
        .select_for_update()
        .all()
    )

    if any(
        item.estado
        == FacturaVencimientoGestion.ESTADO_PAGADO
        for item in vencimientos
    ):
        raise ValidationError(
            "No se puede eliminar un plan "
            "que ya contiene pagos realizados."
        )

    factura.vencimientos_pago.all().delete()

    raw_data = dict(
        factura.raw_data or {}
    )
    snapshot = raw_data.pop(
        SNAPSHOT_KEY,
        None,
    )

    if snapshot:
        factura.estado = (
            snapshot.get("estado")
            or "PENDIENTE"
        )
        factura.fecha_autorizacion_gerencia = (
            _parse_date(
                snapshot.get(
                    "fecha_autorizacion_gerencia"
                )
            )
        )
        factura.fecha_pago_segun_contrato = (
            _parse_date(
                snapshot.get(
                    "fecha_pago_segun_contrato"
                )
            )
        )
        factura.fecha_real_pago = _parse_date(
            snapshot.get("fecha_real_pago")
        )
        factura.importe_pagado = money(
            snapshot.get("importe_pagado")
        )
    else:
        factura.estado = "PENDIENTE"
        factura.fecha_autorizacion_gerencia = None
        factura.fecha_pago_segun_contrato = None
        factura.fecha_real_pago = None
        factura.importe_pagado = Decimal("0.00")

    factura.raw_data = raw_data
    factura.modificado_por = user

    factura.save(update_fields=[
        "estado",
        "fecha_autorizacion_gerencia",
        "fecha_pago_segun_contrato",
        "fecha_real_pago",
        "importe_pagado",
        "raw_data",
        "modificado_por",
        "updated_at",
    ])

    return factura



# FACTURAS_VERITAS_ERRONEOUS_PAYMENT_EVIDENCE_REVERSAL_V2
@transaction.atomic
def revertir_pago_erroneo(*, factura_id, user, team_ids=None, motivo=None):
    """Reverse only derived payment markers; never erase independent payment evidence."""
    from apps.gestion.models import GestionAuditLog

    factura = _scope_factura(factura_id, team_ids)
    vencimientos = list(
        factura.vencimientos_pago.select_for_update().order_by(
            "fecha_vencimiento", "numero_pago", "pk"
        )
    )
    raw = factura.raw_data if isinstance(factura.raw_data, dict) else {}
    independent = []
    for key in (
        "pago_id", "payment_id", "conciliacion_id", "conciliacion_ids",
        "movimiento_bancario_id", "bank_transaction_id", "asiento_id",
        "remesa_id", "transferencia_id",
    ):
        value = raw.get(key)
        if value not in (None, "", 0, False, [], {}):
            independent.append(f"vínculo {key}")
    for item in vencimientos:
        if (item.referencia_pago or "").strip():
            independent.append(f"referencia del vencimiento {item.numero_pago}")
    if independent:
        raise ValidationError(
            "No se puede revertir: existe evidencia independiente ("
            + ", ".join(independent) + ")."
        )
    if (factura.estado or "").strip().upper() != "PAGADA":
        if (factura.estado or "").strip().upper() == "PENDIENTE":
            return factura, False
        raise ValidationError("Solo se puede revertir un marcado PAGADA.")

    before = {
        "estado": factura.estado or "",
        "importe_pagado": str(factura.importe_pagado or Decimal("0.00")),
        "fecha_real_pago": factura.fecha_real_pago.isoformat() if factura.fecha_real_pago else None,
        "vencimientos": [
            {"id": v.pk, "estado": v.estado, "importe_pagado": str(v.importe_pagado or Decimal("0.00")),
             "fecha_real_pago": v.fecha_real_pago.isoformat() if v.fecha_real_pago else None}
            for v in vencimientos
        ],
    }
    for item in vencimientos:
        if item.estado == FacturaVencimientoGestion.ESTADO_PAGADO:
            item.estado = FacturaVencimientoGestion.ESTADO_PENDIENTE
            item.fecha_real_pago = None
            item.importe_pagado = Decimal("0.00")
            item.pagado_por = None
            item.save(update_fields=["estado", "fecha_real_pago", "importe_pagado", "pagado_por", "updated_at"])
    factura.estado = "PENDIENTE"
    factura.importe_pagado = Decimal("0.00")
    factura.fecha_real_pago = None
    factura.modificado_por = user
    factura.save(update_fields=["estado", "importe_pagado", "fecha_real_pago", "modificado_por", "updated_at"])
    after = {
        "estado": factura.estado,
        "importe_pagado": str(factura.importe_pagado),
        "fecha_real_pago": None,
        "vencimientos_pendientes": sum(1 for v in vencimientos if v.estado == FacturaVencimientoGestion.ESTADO_PENDIENTE),
    }
    GestionAuditLog.objects.create(
        team=factura.team, usuario=user, accion="MODIFICADO",
        entidad="FacturaProveedorGestion", objeto_id=factura.pk,
        objeto_repr=factura.cod_factura, factura=factura,
        descripcion=motivo or "Reversión de pago erróneo sin evidencia independiente",
        metadata={
            "operation": "FACTURAS_VERITAS_ERRONEOUS_PAYMENT_EVIDENCE_REVERSAL_V2",
            "before": before, "after": after,
            "independent_evidence": False,
        },
    )
    return factura, True

# FACTURA_PAGO_CORRECCION_SIN_EVIDENCIA_V1
@transaction.atomic
def corregir_estado_pago_sin_evidencia(*, factura_id, user, team_ids=None):
    """Move a PAGADA invoice to PENDIENTE only when no payment evidence exists."""
    from apps.gestion.models import GestionAuditLog

    factura = _scope_factura(factura_id, team_ids)
    vencimientos = list(
        factura.vencimientos_pago.select_for_update().order_by("fecha_vencimiento", "numero_pago")
    )
    estado = (factura.estado or "").strip().upper()
    if estado == "PENDIENTE":
        return factura, False
    if estado != "PAGADA":
        raise ValidationError("Solo se puede corregir una factura en estado PAGADA.")

    razones = []
    if money(factura.importe_pagado) != Decimal("0.00"):
        razones.append("la factura tiene importe pagado")
    if factura.fecha_real_pago is not None:
        razones.append("la factura tiene fecha real de pago")
    for item in vencimientos:
        if item.estado == FacturaVencimientoGestion.ESTADO_PAGADO:
            razones.append(f"el vencimiento {item.numero_pago} está pagado")
        elif money(item.importe_pagado) != Decimal("0.00"):
            razones.append(f"el vencimiento {item.numero_pago} tiene importe pagado")
        elif item.fecha_real_pago is not None:
            razones.append(f"el vencimiento {item.numero_pago} tiene fecha real de pago")
    raw = factura.raw_data if isinstance(factura.raw_data, dict) else {}
    for key in ("pago_id", "payment_id", "conciliacion_id", "movimiento_bancario_id", "bank_transaction_id"):
        if raw.get(key) not in (None, "", 0, False):
            razones.append("existe un vínculo contable o bancario")
            break
    if razones:
        raise ValidationError("No se puede volver a PENDIENTE: " + "; ".join(dict.fromkeys(razones)) + ".")

    before = {
        "estado": factura.estado or "",
        "importe_pagado": str(factura.importe_pagado or Decimal("0.00")),
        "fecha_real_pago": factura.fecha_real_pago.isoformat() if factura.fecha_real_pago else None,
    }
    factura.estado = "PENDIENTE"
    factura.modificado_por = user
    factura.save(update_fields=["estado", "modificado_por", "updated_at"])
    GestionAuditLog.objects.create(
        team=factura.team,
        usuario=user,
        accion="MODIFICADO",
        entidad="FacturaProveedorGestion",
        objeto_id=factura.pk,
        objeto_repr=factura.cod_factura,
        factura=factura,
        descripcion="Corrección de estado PAGADA erróneo sin evidencia real de pago",
        metadata={
            "operation": "FACTURAS_VERITAS_PAYMENT_STATUS_AND_DATE_EDIT_FIX_V1",
            "estado_anterior": before["estado"],
            "estado_nuevo": "PENDIENTE",
            "importe_pagado_anterior": before["importe_pagado"],
            "importe_pagado_nuevo": str(factura.importe_pagado or Decimal("0.00")),
            "fecha_real_pago_anterior": before["fecha_real_pago"],
            "fecha_real_pago_nueva": factura.fecha_real_pago.isoformat() if factura.fecha_real_pago else None,
            "vencimientos_total": len(vencimientos),
            "vencimientos_pagados": 0,
        },
    )
    return factura, True
