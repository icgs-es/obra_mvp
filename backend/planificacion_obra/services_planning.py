
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any, List

from django.apps import apps


ZERO = Decimal("0.00")

MANO_OBRA_TYPES = {"M.O. ADM.", "M.O. CONT.", "PER. CONT."}

MONEY_TOLERANCE = Decimal("0.05")
HOURS_TOLERANCE = Decimal("0.05")


def _dec(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value) -> Decimal:
    return _dec(value).quantize(Decimal("0.01"))


def _resource_type_previsto(row) -> str:
    recurso = getattr(row, "recurso", None)
    tipo = getattr(recurso, "tipo", "") if recurso else ""
    return (tipo or "").strip() or "SIN_TIPO"


def _resource_type_real(row) -> str:
    tipo = (getattr(row, "legacy_tipo_recurso", "") or "").strip()
    if tipo:
        return tipo

    recurso = getattr(row, "recurso", None)
    tipo = getattr(recurso, "tipo", "") if recurso else ""
    return (tipo or "").strip() or "SIN_TIPO"


def _real_cost(row) -> Decimal:
    coste = _dec(getattr(row, "costo_recurso_real", None))
    if coste:
        return coste

    cantidad = _dec(getattr(row, "cantidad", None))
    precio = _dec(getattr(row, "precio_unidad", None))
    return cantidad * precio


def _calc_percent(real: Decimal, previsto: Decimal):
    if not previsto:
        return None
    return ((real / previsto) * Decimal("100")).quantize(Decimal("0.01"))


def _add_group(groups: Dict[str, Dict[str, Any]], tipo: str, cantidad: Decimal, coste: Decimal):
    if tipo not in groups:
        groups[tipo] = {
            "n": 0,
            "cantidad": ZERO,
            "coste": ZERO,
        }

    groups[tipo]["n"] += 1
    groups[tipo]["cantidad"] += cantidad
    groups[tipo]["coste"] += coste


def _warning(code: str, message: str, legacy: Decimal, recalculado: Decimal, tolerance: Decimal):
    diferencia = recalculado - legacy

    if abs(diferencia) <= tolerance:
        return None

    return {
        "code": code,
        "level": "warning",
        "message": message,
        "legacy": legacy,
        "recalculado": recalculado,
        "diferencia": diferencia,
    }


@dataclass
class PlanningTareaSnapshot:
    tarea_id: int
    obra: str
    vivienda: str
    planta: str
    capitulo: str
    partida: str
    unidad: str
    cantidad_tarea: Decimal

    n_previstos: int
    n_reales: int

    # Datos recalculados por portal desde líneas.
    coste_previsto: Decimal
    coste_real: Decimal
    desviacion_coste: Decimal
    desviacion_coste_pct: Decimal | None

    horas_mo_previstas: Decimal
    horas_mo_reales: Decimal
    desviacion_horas_mo: Decimal
    desviacion_horas_mo_pct: Decimal | None

    # Datos legacy/importados desde TareaObra.
    legacy_coste_previsto: Decimal
    legacy_coste_real: Decimal
    legacy_horas_previstas: Decimal
    legacy_horas_reales: Decimal

    estado_calculado: str
    tipos_previstos: Dict[str, Dict[str, Any]]
    tipos_reales: Dict[str, Dict[str, Any]]
    warnings: List[Dict[str, Any]]


def build_tarea_planning_snapshot(tarea_obra) -> PlanningTareaSnapshot:
    """
    Construye un resumen de Planning para una TareaObra.

    Regla central:
    - TareaObra es el eje del Planning.
    - Previsto recalculado: TareaRecursoPrevisto por FK tarea_obra.
    - Real recalculado: TareaRecursoReal por FK tarea_obra.
    - Horas previstas: TareaObra.horas como referencia funcional importada.
    - Horas reales: suma de TareaRecursoReal.cantidad cuando el tipo es mano de obra.
    - Los campos calculados legacy no se aceptan como verdad absoluta:
      se comparan y se generan warnings si difieren del recálculo.
    - No se usa almacén en esta primera versión.
    """

    TRP = apps.get_model("planificacion_obra", "TareaRecursoPrevisto")
    TRR = apps.get_model("planificacion_obra", "TareaRecursoReal")

    previstos = (
        TRP.objects
        .select_related("recurso")
        .filter(tarea_obra=tarea_obra)
    )

    reales = (
        TRR.objects
        .select_related("recurso", "empleado")
        .filter(tarea_obra=tarea_obra)
    )

    tipos_previstos = {}
    tipos_reales = {}
    warnings = []

    n_previstos = 0
    n_reales = 0

    coste_previsto = ZERO
    coste_real = ZERO

    legacy_coste_previsto = _money(getattr(tarea_obra, "importe_tarea", None))
    legacy_coste_real = _money(getattr(tarea_obra, "importe_tarea_real", None))
    legacy_horas_previstas = _dec(getattr(tarea_obra, "horas", None))
    legacy_horas_reales = _dec(getattr(tarea_obra, "horas_reales", None))

    # Regla Planning:
    # Las horas previstas funcionales salen de TareaObra.horas.
    # No usar TareaRecursoPrevisto.cantidad como horas, porque puede ser M2, ML, UD, PA, etc.
    horas_mo_previstas = legacy_horas_previstas
    horas_mo_reales = ZERO

    for row in previstos:
        n_previstos += 1
        tipo = _resource_type_previsto(row)
        cantidad = _dec(row.cantidad)
        coste = _dec(row.costo_recurso)

        coste_previsto += coste
        _add_group(tipos_previstos, tipo, cantidad, coste)

    for row in reales:
        n_reales += 1
        tipo = _resource_type_real(row)
        cantidad = _dec(row.cantidad)
        coste = _real_cost(row)

        coste_real += coste
        _add_group(tipos_reales, tipo, cantidad, coste)

        if tipo in MANO_OBRA_TYPES:
            horas_mo_reales += cantidad

    coste_previsto = _money(coste_previsto)
    coste_real = _money(coste_real)

    desviacion_coste = coste_real - coste_previsto
    desviacion_horas_mo = horas_mo_reales - horas_mo_previstas

    if n_previstos == 0 and n_reales == 0:
        estado = "SIN_DATOS"
    elif n_previstos > 0 and n_reales == 0:
        estado = "PENDIENTE"
    elif n_previstos == 0 and n_reales > 0:
        estado = "REAL_SIN_PREVISTO"
    else:
        estado = "CON_REAL"

    for item in [
        _warning(
            "IMPORTE_PREVISTO_DIFIERE",
            "El importe previsto importado no coincide con la suma de recursos previstos.",
            legacy_coste_previsto,
            coste_previsto,
            MONEY_TOLERANCE,
        ),
        _warning(
            "IMPORTE_REAL_DIFIERE",
            "El importe real importado no coincide con la suma de recursos reales.",
            legacy_coste_real,
            coste_real,
            MONEY_TOLERANCE,
        ),
        _warning(
            "HORAS_REALES_DIFIEREN",
            "Las horas reales importadas no coinciden con la suma de horas reales de mano de obra.",
            legacy_horas_reales,
            horas_mo_reales,
            HOURS_TOLERANCE,
        ),
    ]:
        if item:
            warnings.append(item)

    if n_previstos == 0 and n_reales > 0:
        warnings.append({
            "code": "REAL_SIN_PREVISTO",
            "level": "info",
            "message": "La tarea tiene recursos reales imputados pero no tiene recursos previstos.",
            "legacy": ZERO,
            "recalculado": coste_real,
            "diferencia": coste_real,
        })

    return PlanningTareaSnapshot(
        tarea_id=tarea_obra.id,
        obra=str(getattr(tarea_obra, "obra", "") or "-"),
        vivienda=str(getattr(tarea_obra, "legacy_cod_vivienda", "") or "-"),
        planta=str(getattr(tarea_obra, "legacy_planta", "") or "-"),
        capitulo=str(getattr(tarea_obra, "legacy_capitulo", "") or "-"),
        partida=str(getattr(tarea_obra, "legacy_partida", "") or "-"),
        unidad=str(getattr(tarea_obra, "unidad", "") or "-"),
        cantidad_tarea=_dec(getattr(tarea_obra, "cantidad", None)),

        n_previstos=n_previstos,
        n_reales=n_reales,

        coste_previsto=coste_previsto,
        coste_real=coste_real,
        desviacion_coste=_money(desviacion_coste),
        desviacion_coste_pct=_calc_percent(coste_real, coste_previsto),

        horas_mo_previstas=_dec(horas_mo_previstas),
        horas_mo_reales=_dec(horas_mo_reales),
        desviacion_horas_mo=_dec(desviacion_horas_mo),
        desviacion_horas_mo_pct=_calc_percent(horas_mo_reales, horas_mo_previstas),

        legacy_coste_previsto=legacy_coste_previsto,
        legacy_coste_real=legacy_coste_real,
        legacy_horas_previstas=legacy_horas_previstas,
        legacy_horas_reales=legacy_horas_reales,

        estado_calculado=estado,
        tipos_previstos=tipos_previstos,
        tipos_reales=tipos_reales,
        warnings=warnings,
    )
