"""Informe read-only de materiales realmente asignados a obra."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.urls import reverse

from apps.gestion.models import (
    AlbaranProveedorGestion,
    AlbaranProveedorLineaGestion,
    FacturaAlbaranGestion,
    FacturaProveedorGestion,
    FacturaProveedorLineaGestion,
)
from .models import TareaRecursoReal

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _dec(value):
    return Decimal(str(value or "0"))


def _q2(value):
    return _dec(value).quantize(CENT, rounding=ROUND_HALF_UP)


def format_decimal_es(value, places):
    if value is None:
        return "—"
    return f"{_dec(value):,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_money_es(value):
    return "—" if value is None else f"{format_decimal_es(value, 2)} €"


def materiales_queryset(obra):
    """Una fila real canónica; nunca documentos o movimientos como filas."""
    return (
        TareaRecursoReal.objects.filter(
            team_id=obra.team_id,
            legacy_cod_obra=obra.legacy_cod_obra,
            recurso__isnull=False,
            empleado__isnull=True,
        )
        .exclude(legacy_tipo_recurso__istartswith="M.O.")
        .select_related(
            "team", "recurso", "tarea_obra", "tarea_obra__obra", "tarea_obra__unidad_obra",
            "tarea_obra__capitulo", "tarea_obra__partida", "tarea_obra__partida__capitulo",
            "unidad_obra", "unidad_obra__fase",
            "partida", "partida__capitulo", "movimiento_almacen", "empleado",
        )
        .order_by("-inicio_recurso_real", "-created_at", "-pk")
    )


def _apply_filters(qs, filters):
    if filters.get("desde"):
        qs = qs.filter(inicio_recurso_real__gte=filters["desde"])
    if filters.get("hasta"):
        qs = qs.filter(inicio_recurso_real__lte=filters["hasta"])
    if filters.get("recurso"):
        qs = qs.filter(recurso_id=filters["recurso"])
    if filters.get("fase"):
        qs = qs.filter(legacy_cod_fase=filters["fase"])
    if filters.get("vivienda"):
        qs = qs.filter(Q(legacy_cod_vivienda=filters["vivienda"]) | Q(unidad_obra_id=filters["vivienda"]))
    if filters.get("planta"):
        qs = qs.filter(legacy_planta=filters["planta"])
    if filters.get("capitulo"):
        qs = qs.filter(Q(tarea_obra__capitulo_id=filters["capitulo"]) | Q(partida__capitulo_id=filters["capitulo"]))
    if filters.get("partida"):
        qs = qs.filter(Q(tarea_obra__partida_id=filters["partida"]) | Q(partida_id=filters["partida"]))
    return qs


def _document_maps(rows, team_id):
    albaran_codes = {r.cod_albaran for r in rows if r.cod_albaran}
    factura_codes = {r.cod_factura for r in rows if r.cod_factura}
    albaranes = {a.cod_albaran: a for a in AlbaranProveedorGestion.objects.filter(team_id=team_id, cod_albaran__in=albaran_codes).select_related("proveedor")}
    facturas = {f.cod_factura: f for f in FacturaProveedorGestion.objects.filter(team_id=team_id, cod_factura__in=factura_codes).select_related("proveedor")}

    albaran_ids = [a.pk for a in albaranes.values()]
    links = defaultdict(list)
    for link in FacturaAlbaranGestion.objects.filter(team_id=team_id, albaran_id__in=albaran_ids).select_related("factura", "factura__proveedor"):
        links[link.albaran_id].append(link.factura)
        facturas.setdefault(link.factura.cod_factura, link.factura)

    al_lines = defaultdict(list)
    for line in AlbaranProveedorLineaGestion.objects.filter(albaran_id__in=albaran_ids).select_related("articulo_compra"):
        al_lines[(line.albaran_id, line.linea)].append(line)
    fac_ids = [f.pk for f in facturas.values()]
    fac_lines = defaultdict(list)
    for line in FacturaProveedorLineaGestion.objects.filter(factura_id__in=fac_ids).select_related("articulo_compra", "albaran"):
        fac_lines[(line.factura_id, line.linea)].append(line)
    return albaranes, facturas, links, al_lines, fac_lines


def _invoice_line(real, factura, albaran, fac_lines):
    candidates = []
    if factura and real.num_linea_factura:
        candidates += fac_lines.get((factura.pk, real.num_linea_factura), [])
    if factura and albaran:
        for (fid, _line_no), lines in fac_lines.items():
            if fid != factura.pk:
                continue
            for line in lines:
                if line.albaran_id == albaran.pk and (
                    not real.num_linea_albaran or line.linea_albaran_legacy == real.num_linea_albaran
                ):
                    candidates.append(line)
    unique = {x.pk: x for x in candidates}
    return list(unique.values())


def _line_unit_price(line):
    qty = _dec(line.cantidad)
    if qty == 0:
        return None
    # `importe_linea` es la base neta canónica: los formularios documentales
    # ya descuentan importe_descuento al calcularla. Restarlo de nuevo
    # infravaloraría históricos con descuento.
    net = _dec(line.importe_linea)
    if net == 0 and _dec(line.precio_unitario) != 0 and not (
        _dec(getattr(line, "importe_descuento", 0)) or _dec(getattr(line, "descuento", 0))
    ):
        return _dec(line.precio_unitario)
    return net / qty


def build_materiales_report(obra, filters=None, can_view_amounts=True, can_view_albaran=True, can_view_factura=True):
    filters = filters or {}
    qs = _apply_filters(materiales_queryset(obra), filters)
    rows = list(qs)
    albaranes, facturas, links, al_lines, fac_lines = _document_maps(rows, obra.team_id)
    details = []

    for real in rows:
        albaran = albaranes.get(real.cod_albaran)
        factura = facturas.get(real.cod_factura)
        linked = links.get(albaran.pk, []) if albaran else []
        ambiguous = False
        if not factura and len(linked) == 1:
            factura = linked[0]
        elif not factura and len(linked) > 1:
            ambiguous = True

        al_candidates = al_lines.get((albaran.pk, real.num_linea_albaran), []) if albaran and real.num_linea_albaran else []
        invoice_candidates = _invoice_line(real, factura, albaran, fac_lines)
        if len(invoice_candidates) > 1 or len(al_candidates) > 1:
            ambiguous = True

        price = None
        valuation_source = "SIN_VALORACION"
        iva_rate = None
        if not ambiguous and len(invoice_candidates) == 1:
            price = _line_unit_price(invoice_candidates[0])
            valuation_source = "FACTURA"
            if factura and _dec(factura.importe_base_imponible) != 0:
                iva_rate = _dec(factura.importe_iva) / _dec(factura.importe_base_imponible)
        elif not ambiguous and len(al_candidates) == 1:
            price = _line_unit_price(al_candidates[0])
            valuation_source = "ALBARAN"
        elif not ambiguous and (_dec(real.precio_unidad) != 0 or _dec(real.costo_recurso_real) != 0):
            price = _dec(real.precio_unidad)
            if price == 0 and _dec(real.cantidad) != 0:
                price = _dec(real.costo_recurso_real or real.costo_recurso) / _dec(real.cantidad)
            valuation_source = "ASIGNACION_REAL"

        quantity = _dec(real.cantidad)
        base = _q2(quantity * price) if price is not None else None
        iva = _q2(base * iva_rate) if base is not None and iva_rate is not None else None
        # Total conservador: base demostrada + solo el IVA atribuible.
        # Cuando el IVA no es inequívoco se suma cero y se muestra advertencia.
        total = _q2(base + (iva or ZERO)) if base is not None else None

        movement = real.movimiento_almacen
        raw = real.raw_data if isinstance(real.raw_data, dict) else {}
        if movement:
            origin = "ALMACÉN"
        elif real.cod_albaran:
            origin = "ALBARÁN"
        elif real.cod_factura:
            origin = "FACTURA"
        elif raw.get("source") == "portal_asignacion_obra" or "manual" in str(raw.get("source", "")).lower():
            origin = "MANUAL"
        else:
            origin = "LEGACY"

        warning = ""
        state = "VALORADO"
        if ambiguous:
            state, warning = "AMBIGUO", "Varias relaciones documentales posibles"
            base = iva = total = price = None
        elif base is None:
            state, warning = "SIN_VALORACION", "Sin precio histórico demostrable"
        elif iva is None:
            warning = "IVA no atribuible de forma inequívoca"
        trace_warnings = []
        if real.cod_albaran and not albaran:
            trace_warnings.append("Albarán legacy no resuelto")
        if real.cod_factura and not factura:
            trace_warnings.append("Factura legacy no resuelta")
        if trace_warnings:
            warning = "; ".join(([warning] if warning else []) + trace_warnings)

        provider = (factura.proveedor if factura and factura.proveedor_id else None) or (albaran.proveedor if albaran and albaran.proveedor_id else None)
        item = {
            "id": real.pk, "identity": f"TareaRecursoReal:{real.pk}", "real": real,
            "date": real.inicio_recurso_real, "resource_id": real.recurso_id,
            "code": real.recurso.legacy_id, "article": real.recurso.nombre,
            "unit": real.unidad or real.recurso.unidad, "quantity": quantity,
            "price": price if can_view_amounts else None, "base": base if can_view_amounts else None,
            "iva": iva if can_view_amounts else None, "total": total if can_view_amounts else None,
            "origin": origin, "albaran": albaran, "factura": factura,
            "albaran_url": reverse("gestion:albaran_detail", args=[albaran.pk]) if albaran and can_view_albaran else "",
            "factura_url": reverse("gestion:factura_detail", args=[factura.pk]) if factura and can_view_factura else "",
            "document_date": factura.fecha_emision if valuation_source == "FACTURA" and factura else (albaran.fecha_albaran if albaran else None),
            "provider": provider, "phase": real.unidad_obra.fase.nombre if real.unidad_obra_id and real.unidad_obra.fase_id else real.legacy_cod_fase,
            "housing": real.unidad_obra.vivienda if real.unidad_obra_id else real.legacy_cod_vivienda,
            "floor": real.legacy_planta, "chapter": real.tarea_obra.capitulo if real.tarea_obra_id else (real.partida.capitulo if real.partida_id else None),
            "partida": real.tarea_obra.partida if real.tarea_obra_id else real.partida,
            "task": real.tarea_obra, "valuation_source": valuation_source, "valuation_state": state,
            "warning": warning, "warning_label": warning,
        }
        item["quantity_display"] = format_decimal_es(quantity, 1)
        item["price_display"] = format_money_es(item["price"])
        item["net_total"] = item["base"]
        item["net_total_display"] = format_money_es(item["net_total"])
        chapter = item["chapter"]
        partida = item["partida"]
        chapter_text = f"{chapter.codigo} · {chapter.nombre}" if chapter else (real.legacy_capitulo or "—")
        partida_text = f"{partida.codigo} · {partida.nombre}" if partida else (real.legacy_partida or "—")
        task_text = str(real.tarea_obra.observaciones or real.tarea_obra.programacion or "").strip() if real.tarea_obra_id else ""
        unit = real.unidad_obra if real.unidad_obra_id else None
        destination_floor = item["floor"] or (unit.nivel if unit else "")
        item["destination"] = " · ".join(x for x in [
            f"Vivienda {item['housing']}" if item["housing"] else "",
            str(destination_floor or ""), chapter_text, partida_text, task_text,
        ] if x and x != "—") or "—"
        doc_bits = []
        if albaran:
            doc_bits.append(f"Albarán {albaran.cod_albaran}")
        if factura:
            prefix = "Valorado mediante factura" if origin == "ALBARÁN" else "Factura"
            doc_bits.append(f"{prefix} {factura.cod_factura}")
        item["origin_title"] = " · ".join(doc_bits) or warning or origin.title()
        details.append(item)

    provider_filter = str(filters.get("proveedor") or "")
    doc_filter = filters.get("documento") or "TODOS"
    val_filter = filters.get("valoracion") or "TODOS"
    if provider_filter:
        details = [x for x in details if x["provider"] and str(x["provider"].pk) == provider_filter]
    if doc_filter != "TODOS":
        details = [x for x in details if (
            (doc_filter == "ALBARAN" and x["albaran"] and not x["factura"]) or
            (doc_filter == "FACTURA" and x["factura"] and not x["albaran"]) or
            (doc_filter == "ALBARAN_FACTURADO" and x["albaran"] and x["factura"]) or
            (doc_filter == "ALMACEN" and x["origin"] == "ALMACÉN") or
            (doc_filter == "MANUAL" and x["origin"] == "MANUAL") or
            (doc_filter == "SIN_DOCUMENTO" and not x["albaran"] and not x["factura"])
        )]
    if val_filter != "TODOS":
        details = [x for x in details if x["valuation_state"] == val_filter]

    summary_map = {}
    for item in details:
        key = item["resource_id"]
        row = summary_map.setdefault(key, {
            "resource_id": key, "code": item["code"], "article": item["article"], "unit": item["unit"],
            "quantity": ZERO, "assignments": 0, "partitions": set(), "documents": set(),
            "base": ZERO, "iva": ZERO, "total": ZERO, "unvalued_quantity": ZERO, "warnings": 0,
            "prices": set(),
        })
        row["quantity"] += item["quantity"]
        row["assignments"] += 1
        if item["partida"]:
            row["partitions"].add(item["partida"].pk)
        if item["albaran"]:
            row["documents"].add(("A", item["albaran"].pk))
        if item["factura"]:
            row["documents"].add(("F", item["factura"].pk))
        if item["base"] is None:
            row["unvalued_quantity"] += item["quantity"]
        else:
            row["base"] += item["base"]
            if item["price"] is not None:
                row["prices"].add(_q2(item["price"]))
        if item["iva"] is not None:
            row["iva"] += item["iva"]
        if item["total"] is not None:
            row["total"] += item["total"]
        if item["warning"]:
            row["warnings"] += 1
    summary = sorted(summary_map.values(), key=lambda x: (str(x["article"]).casefold(), x["resource_id"]))
    for row in summary:
        row["partitions_count"] = len(row.pop("partitions")); row["documents_count"] = len(row.pop("documents"))
        prices = row.pop("prices")
        row["quantity_display"] = format_decimal_es(row["quantity"], 1)
        row["price_display"] = format_money_es(next(iter(prices))) if len(prices) == 1 else ("Varios" if prices else "—")
        row["net_total"] = row["base"]
        row["net_total_display"] = format_money_es(row["net_total"])

    totals = {
        "assignments": len(details), "articles": len(summary),
        "documents": len({(k, x[k].pk) for x in details for k in ("albaran", "factura") if x[k]}),
        "base": _q2(sum((x["base"] for x in details if x["base"] is not None), ZERO)),
        "iva": _q2(sum((x["iva"] for x in details if x["iva"] is not None), ZERO)),
        "total": _q2(sum((x["total"] for x in details if x["total"] is not None), ZERO)),
        "unvalued": sum(1 for x in details if x["valuation_state"] == "SIN_VALORACION"),
        "ambiguous": sum(1 for x in details if x["valuation_state"] == "AMBIGUO"),
    }
    totals["net_total"] = totals["base"]
    totals["net_total_display"] = format_money_es(totals["net_total"])
    return {"details": details, "summary": summary, "totals": totals}


def csv_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
