"""
Reglas centralizadas para eliminar albaranes y sus líneas.

Un albarán puede eliminarse con independencia de su posición en la
numeración, pero únicamente cuando no tenga incidencia documental u
operativa en facturas, almacén o planificación de obra.
"""

from decimal import Decimal

from django.apps import apps
from django.db.models import Q


ALBARAN_DELETE_PERMISSION = (
    "gestion.delete_albaranproveedorgestion"
)


def can_user_delete_albaran(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.has_perm(
                ALBARAN_DELETE_PERMISSION
            )
        )
    )


def _decimal(value):
    try:
        return Decimal(
            str(value or "0")
        )
    except Exception:
        return Decimal("0")


def _has_value(value):
    return value not in (
        None,
        "",
        False,
        0,
        "0",
        "0.0",
        "0.0000",
        [],
        {},
    )


def _append_blocker(
    blockers,
    code,
    message,
):
    if any(
        blocker["code"] == code
        for blocker in blockers
    ):
        return

    blockers.append({
        "code": code,
        "message": message,
    })


def static_line_blockers(line):
    """
    Indicadores persistidos directamente en la línea.

    Estos indicadores se consideran bloqueantes incluso cuando el
    registro operativo histórico no tenga una FK directa.
    """
    blockers = []

    if bool(
        getattr(
            line,
            "facturado",
            False,
        )
    ):
        _append_blocker(
            blockers,
            "FACTURADA",
            "está marcada como facturada",
        )

    if str(
        getattr(
            line,
            "factura_legacy",
            "",
        )
        or ""
    ).strip():
        _append_blocker(
            blockers,
            "FACTURA_LEGACY",
            "conserva una referencia de factura",
        )

    if bool(
        getattr(
            line,
            "en_almacen",
            False,
        )
    ):
        _append_blocker(
            blockers,
            "EN_ALMACEN",
            "está incorporada a almacén",
        )

    if getattr(
        line,
        "id_almacen_legacy",
        None,
    ):
        _append_blocker(
            blockers,
            "ID_ALMACEN",
            "conserva un identificador de almacén",
        )

    if bool(
        getattr(
            line,
            "en_partida",
            False,
        )
    ):
        _append_blocker(
            blockers,
            "EN_PARTIDA",
            "está asignada a una partida de obra",
        )

    if _decimal(
        getattr(
            line,
            "cantidad_en_partidas",
            0,
        )
    ) > 0:
        _append_blocker(
            blockers,
            "CANTIDAD_PARTIDA",
            "tiene cantidad imputada a partidas",
        )

    raw_data = (
        getattr(
            line,
            "raw_data",
            {},
        )
    )

    if not isinstance(
        raw_data,
        dict,
    ):
        raw_data = {}

    warehouse_markers = (
        "movimiento_almacen_id",
        "movimiento_entrada_almacen_id",
        "movimiento_salida_almacen_id",
        "en_almacen_desde",
    )

    for key in warehouse_markers:
        if _has_value(
            raw_data.get(key)
        ):
            _append_blocker(
                blockers,
                "RAW_ALMACEN",
                (
                    "conserva trazabilidad de "
                    "un movimiento de almacén"
                ),
            )
            break

    planning_markers = (
        "tarea_recurso_real_id",
        "en_partida_desde",
        "partidas_asignadas",
        "imputaciones",
        "imputaciones_partida",
    )

    for key in planning_markers:
        if _has_value(
            raw_data.get(key)
        ):
            _append_blocker(
                blockers,
                "RAW_PARTIDA",
                (
                    "conserva trazabilidad de "
                    "una imputación a obra"
                ),
            )
            break

    return blockers


def _warehouse_movement_ids(
    albaran,
    line,
):
    Movimiento = apps.get_model(
        "planificacion_obra",
        "RecursoAlmacenMovimiento",
    )

    query = Q(
        raw_data__albaran_linea_id=line.pk,
    )

    query |= Q(
        raw_data__albaran_id=albaran.pk,
        raw_data__linea=line.linea,
    )

    query |= (
        Q(
            raw_data__documento_id=albaran.pk,
            raw_data__linea_id=line.pk,
        )
        & (
            Q(
                raw_data__source__icontains=(
                    "albaran"
                ),
            )
            | Q(
                raw_data__origen_tipo__iexact=(
                    "ALBARAN"
                ),
            )
        )
    )

    codigo = str(
        albaran.cod_albaran
        or ""
    ).strip()

    if codigo:
        query |= Q(
            cod_albaran=codigo,
            linea=line.linea,
        )

    return list(
        Movimiento.objects
        .filter(query)
        .order_by("pk")
        .values_list(
            "pk",
            flat=True,
        )
        .distinct()
    )


def _planning_real_ids(
    albaran,
    line,
):
    Real = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )

    query = Q(
        raw_data__origen_tipo__iexact=(
            "ALBARAN"
        ),
        raw_data__documento_id=albaran.pk,
        raw_data__linea_id=line.pk,
    )

    query |= (
        Q(
            raw_data__documento_id=albaran.pk,
            raw_data__linea_id=line.pk,
        )
        & Q(
            raw_data__source__icontains=(
                "albaran"
            ),
        )
    )

    codigo = str(
        albaran.cod_albaran
        or ""
    ).strip()

    if codigo:
        query |= Q(
            cod_albaran=codigo,
            num_linea_albaran=line.linea,
        )

    return list(
        Real.objects
        .filter(query)
        .order_by("pk")
        .values_list(
            "pk",
            flat=True,
        )
        .distinct()
    )


def _invoice_line_exists(
    albaran,
    line,
):
    LineaFactura = apps.get_model(
        "gestion",
        "FacturaProveedorLineaGestion",
    )

    return (
        LineaFactura.objects
        .filter(
            albaran=albaran,
            linea_albaran_legacy=line.linea,
        )
        .exists()
    )


def analyze_line_dependencies(
    line,
    albaran=None,
):
    albaran = (
        albaran
        or line.albaran
    )

    blockers = static_line_blockers(
        line
    )

    invoice_line = (
        _invoice_line_exists(
            albaran,
            line,
        )
    )

    if invoice_line:
        _append_blocker(
            blockers,
            "FACTURA_LINEA",
            "tiene una línea de factura vinculada",
        )

    warehouse_ids = (
        _warehouse_movement_ids(
            albaran,
            line,
        )
    )

    if warehouse_ids:
        _append_blocker(
            blockers,
            "MOVIMIENTO_ALMACEN",
            (
                "está asociada a movimiento(s) "
                "de almacén "
                + ", ".join(
                    str(pk)
                    for pk in warehouse_ids[:10]
                )
            ),
        )

    planning_ids = (
        _planning_real_ids(
            albaran,
            line,
        )
    )

    if planning_ids:
        _append_blocker(
            blockers,
            "TAREA_RECURSO_REAL",
            (
                "está imputada a partida(s) "
                "mediante recurso(s) real(es) "
                + ", ".join(
                    str(pk)
                    for pk in planning_ids[:10]
                )
            ),
        )

    return {
        "line_id": line.pk,
        "line_number": line.linea,
        "blockers": blockers,
        "warehouse_ids": warehouse_ids,
        "planning_ids": planning_ids,
        "can_delete": not blockers,
    }


def _relation_exists(
    instance,
    relation_name,
):
    try:
        return bool(
            getattr(
                instance,
                relation_name,
            ).exists()
        )
    except Exception:
        return False


def _direct_warehouse_ids(
    albaran,
):
    Movimiento = apps.get_model(
        "planificacion_obra",
        "RecursoAlmacenMovimiento",
    )

    query = Q(
        raw_data__albaran_id=albaran.pk,
    )

    query |= (
        Q(
            raw_data__documento_id=albaran.pk,
        )
        & (
            Q(
                raw_data__source__icontains=(
                    "albaran"
                ),
            )
            | Q(
                raw_data__origen_tipo__iexact=(
                    "ALBARAN"
                ),
            )
        )
    )

    codigo = str(
        albaran.cod_albaran
        or ""
    ).strip()

    if codigo:
        query |= Q(
            cod_albaran=codigo,
        )

    return list(
        Movimiento.objects
        .filter(query)
        .order_by("pk")
        .values_list(
            "pk",
            flat=True,
        )
        .distinct()
    )


def _direct_planning_ids(
    albaran,
):
    Real = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )

    query = Q(
        raw_data__origen_tipo__iexact=(
            "ALBARAN"
        ),
        raw_data__documento_id=albaran.pk,
    )

    query |= (
        Q(
            raw_data__documento_id=albaran.pk,
        )
        & Q(
            raw_data__source__icontains=(
                "albaran"
            ),
        )
    )

    codigo = str(
        albaran.cod_albaran
        or ""
    ).strip()

    if codigo:
        query |= Q(
            cod_albaran=codigo,
        )

    return list(
        Real.objects
        .filter(query)
        .order_by("pk")
        .values_list(
            "pk",
            flat=True,
        )
        .distinct()
    )


def analyze_albaran_dependencies(
    albaran,
):
    lines = list(
        albaran.lineas
        .all()
        .order_by(
            "linea",
            "pk",
        )
    )

    blockers = []

    invoice_line_link = (
        _relation_exists(
            albaran,
            "lineas_factura",
        )
    )

    invoice_document_link = (
        _relation_exists(
            albaran,
            "facturas_vinculadas",
        )
    )

    if (
        invoice_line_link
        or invoice_document_link
        or bool(
            albaran.asignado_factura
        )
    ):
        blockers.append(
            (
                "El albarán está vinculado "
                "o asignado a una factura."
            )
        )

    if (
        bool(
            albaran.asignado_partida_obra
        )
        or int(
            albaran.lineas_asignadas
            or 0
        ) > 0
    ):
        blockers.append(
            (
                "La cabecera del albarán indica "
                "asignaciones a partidas de obra."
            )
        )

    direct_warehouse_ids = (
        _direct_warehouse_ids(
            albaran
        )
    )

    if direct_warehouse_ids:
        blockers.append(
            (
                "El albarán tiene movimientos "
                "de almacén asociados: "
                + ", ".join(
                    str(pk)
                    for pk
                    in direct_warehouse_ids[:15]
                )
                + "."
            )
        )

    direct_planning_ids = (
        _direct_planning_ids(
            albaran
        )
    )

    if direct_planning_ids:
        blockers.append(
            (
                "El albarán tiene imputaciones "
                "a obra asociadas: "
                + ", ".join(
                    str(pk)
                    for pk
                    in direct_planning_ids[:15]
                )
                + "."
            )
        )

    line_results = [
        analyze_line_dependencies(
            line,
            albaran,
        )
        for line in lines
    ]

    blocked_lines = [
        result
        for result in line_results
        if not result["can_delete"]
    ]

    for result in blocked_lines:
        reasons = "; ".join(
            blocker["message"]
            for blocker
            in result["blockers"]
        )

        blockers.append(
            (
                f"Línea "
                f"{result['line_number']}: "
                f"{reasons}."
            )
        )

    attachment_count = 0

    try:
        attachment_count = (
            albaran.adjuntos.count()
        )
    except Exception:
        attachment_count = 0

    return {
        "can_delete": not blockers,
        "blockers": blockers,
        "lines": line_results,
        "blocked_lines": blocked_lines,
        "line_count": len(lines),
        "attachment_count": (
            attachment_count
        ),
        "invoice_line_link": (
            invoice_line_link
        ),
        "invoice_document_link": (
            invoice_document_link
        ),
        "warehouse_ids": (
            direct_warehouse_ids
        ),
        "planning_ids": (
            direct_planning_ids
        ),
    }
