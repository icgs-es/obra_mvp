from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter
def money_es(value, symbol="€"):
    """
    Formatea importes con criterio español:
    4072266.44 -> 4.072.266,44 €
    """
    if value is None or value == "":
        return "—"

    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return value

    negative = amount < 0
    amount = abs(amount)

    formatted = f"{amount:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    if negative:
        formatted = "-" + formatted

    if symbol:
        return f"{formatted} {symbol}"

    return formatted



@register.filter
def estado_factura_class(value):
    estado = (value or "").strip().upper()

    mapping = {
        "PAGADA": "estado-factura-pagada",
        # FACTURA_PAGOS_MULTIPLES_ESTADOS_V1
        "AUT. PAGO": "estado-factura-pagare",
        "PARCIAL": "estado-factura-pendiente",
        "PENDIENTE": "estado-factura-pendiente",
        "VENCIDA": "estado-factura-vencida",
        "PAGARE ENTR.": "estado-factura-pagare",
        "PAGARÉ ENTR.": "estado-factura-pagare",
    }

    return mapping.get(estado, "estado-factura-otro")



# === ALBARAN_PARTIDA_BADGE_V2 ===
@register.filter
def albaran_partida_badge(albaran):
    from decimal import Decimal, InvalidOperation
    from django.apps import apps
    from django.utils.safestring import mark_safe

    def dec(v):
        try:
            return Decimal(str(v or "0").replace(",", "."))
        except InvalidOperation:
            return Decimal("0")

    def fmt(v):
        try:
            return f"{Decimal(v).quantize(Decimal('0.0000'))}".replace(".", ",")
        except Exception:
            return "0,0000"

    if not albaran:
        return mark_safe('<span class="badge bg-secondary">No</span>')

    Linea = apps.get_model("gestion", "AlbaranProveedorLineaGestion")
    lineas = Linea.objects.filter(albaran_id=albaran.id).only("cantidad", "cantidad_en_partidas")

    total = Decimal("0.0000")
    asignado = Decimal("0.0000")

    for l in lineas:
        cantidad = dec(l.cantidad)
        cantidad_asignada = dec(l.cantidad_en_partidas)

        if cantidad < 0:
            cantidad = Decimal("0.0000")

        if cantidad_asignada < 0:
            cantidad_asignada = Decimal("0.0000")

        if cantidad_asignada > cantidad:
            cantidad_asignada = cantidad

        total += cantidad
        asignado += cantidad_asignada

    if total <= 0 or asignado <= 0:
        return mark_safe('<span class="badge bg-secondary">No</span>')

    if asignado >= total:
        return mark_safe(
            f'<span class="badge bg-primary">Sí</span> '
            f'<span class="small text-muted">{fmt(asignado)} / {fmt(total)}</span>'
        )

    return mark_safe(
        f'<span class="badge bg-warning text-dark">Parcial</span> '
        f'<span class="small text-muted">{fmt(asignado)} / {fmt(total)}</span>'
    )



# === FACTURA_LINEA_TOTAL_IVA_DISPLAY_V1 ===
def _gestion_linea_dec_v1(value, default="0"):
    from decimal import Decimal, InvalidOperation
    import re

    if value is None:
        return Decimal(default)

    s = str(value).strip()
    if not s:
        return Decimal(default)

    s = (
        s.replace("€", "")
         .replace("EUR", "")
         .replace("\u00a0", "")
         .replace(" ", "")
         .replace("'", "")
    )

    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s or s in {"-", ".", ","}:
        return Decimal(default)

    negative = s.startswith("-")
    if negative:
        s = s[1:]

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            s = "".join(parts)

    if negative:
        s = "-" + s

    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(default)


def _gestion_linea_fmt_es_v1(value, places=2):
    from decimal import Decimal

    d = _gestion_linea_dec_v1(value)
    q = Decimal("1").scaleb(-places)
    d = d.quantize(q)

    sign = "-" if d < 0 else ""
    d_abs = abs(d)
    s = f"{d_abs:,.{places}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return sign + s


def _gestion_linea_raw_v1(linea, *keys):
    raw = getattr(linea, "raw_data", None)

    if isinstance(raw, dict):
        for k in keys:
            if k in raw and raw.get(k) not in (None, ""):
                return raw.get(k)

        # Algunos importadores guardan la línea original anidada.
        for nested_key in ("linea", "linea_ocr", "ocr", "payload", "source", "raw"):
            nested = raw.get(nested_key)
            if isinstance(nested, dict):
                for k in keys:
                    if k in nested and nested.get(k) not in (None, ""):
                        return nested.get(k)

    for k in keys:
        if hasattr(linea, k):
            val = getattr(linea, k)
            if val not in (None, ""):
                return val

    return None


@register.filter
def factura_linea_descuento_display(linea):
    """
    Descuento visible de línea.
    Prioriza importe_descuento; si no existe, muestra descuento bruto/importado.
    """
    val = _gestion_linea_raw_v1(
        linea,
        "importe_descuento",
        "descuento_importe",
        "dto_importe",
        "descuento",
        "descuento_raw",
    )

    if val in (None, ""):
        return "0,00"

    return _gestion_linea_fmt_es_v1(val, 2)


@register.filter
def factura_linea_iva_display(linea):
    val = _gestion_linea_raw_v1(
        linea,
        "iva_porcentaje",
        "porcentaje_iva",
        "iva_pct",
        "tasa_iva",
        "tasa",
    )

    if val in (None, ""):
        # Si no hay dato, no inventar; mostrar guion.
        return "—"

    return _gestion_linea_fmt_es_v1(val, 2) + " %"


@register.filter
def factura_linea_total_iva_display(linea):
    """
    Total con IVA de la línea.
    Si el OCR/importador guardó importe_total_con_iva, se usa.
    Si no, se calcula desde base + IVA si hay tasa.
    """
    total = _gestion_linea_raw_v1(
        linea,
        "importe_total_con_iva",
        "total_con_iva",
        "importe_tti",
        "importe_total",
        "total_tti",
    )

    if total not in (None, ""):
        return _gestion_linea_fmt_es_v1(total, 2)

    base = _gestion_linea_raw_v1(linea, "importe_linea")
    iva = _gestion_linea_raw_v1(linea, "iva_porcentaje", "porcentaje_iva", "iva_pct", "tasa_iva", "tasa")

    if base not in (None, "") and iva not in (None, ""):
        b = _gestion_linea_dec_v1(base)
        p = _gestion_linea_dec_v1(iva)
        return _gestion_linea_fmt_es_v1(b * (1 + p / 100), 2)

    if base not in (None, ""):
        return _gestion_linea_fmt_es_v1(base, 2)

    return "0,00"


@register.filter
def factura_linea_tipo_display(linea):
    val = _gestion_linea_raw_v1(linea, "tipo_linea")
    return val or "—"



# === FACTURA_LINEA_CODIGO_PROVEEDOR_SAFE_V1 ===
@register.filter
def factura_linea_codigo_proveedor_display(linea):
    """
    Devuelve un código visible de línea sin romper si el modelo no tiene
    codigo_proveedor. Prioridad:
    raw_data.codigo_proveedor / codigo_detectado / referencia /
    cod_articulo_legacy / codigo, y finalmente atributos reales del modelo.
    """
    raw = getattr(linea, "raw_data", None)

    keys = (
        "codigo_proveedor",
        "codigo_detectado",
        "referencia",
        "cod_articulo_legacy",
        "codigo",
        "cod_articulo",
        "codigo_articulo",
    )

    if isinstance(raw, dict):
        for key in keys:
            val = raw.get(key)
            if val not in (None, ""):
                return str(val)

        for nested_key in ("linea", "linea_ocr", "ocr", "payload", "source", "raw"):
            nested = raw.get(nested_key)
            if isinstance(nested, dict):
                for key in keys:
                    val = nested.get(key)
                    if val not in (None, ""):
                        return str(val)

    for key in keys:
        if hasattr(linea, key):
            val = getattr(linea, key)
            if val not in (None, ""):
                return str(val)

    art = getattr(linea, "articulo_compra", None)
    if art is not None:
        for key in ("codigo", "codigo_interno", "legacy_id"):
            if hasattr(art, key):
                val = getattr(art, key)
                if val not in (None, ""):
                    return str(val)

    return "—"


# === PORTAL INTASA · FACTURA_LINEA_DISPLAY_COMPLETO_V1 ===
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.apps import apps


def _portal_linea_dec_v1(value, default="0.00"):
    if value in (None, ""):
        value = default

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    raw = str(value).replace("€", "").strip()

    # Formato español 1.234,56
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _portal_money_es_v1(value):
    d = _portal_linea_dec_v1(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{d:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _portal_raw_v1(obj):
    raw = getattr(obj, "raw_data", None) or {}
    return raw if isinstance(raw, dict) else {}


def _portal_first_text_v1(obj, keys):
    raw = _portal_raw_v1(obj)
    for k in keys:
        v = raw.get(k)
        if v not in (None, ""):
            return str(v).strip()

    for k in keys:
        if hasattr(obj, k):
            v = getattr(obj, k)
            if v not in (None, ""):
                return str(v).strip()

    return ""


def _portal_model_text_v1(instance):
    if not instance:
        return ""

    for field in ("nombre", "descripcion", "concepto", "titulo", "referencia"):
        if hasattr(instance, field):
            val = getattr(instance, field)
            if val not in (None, ""):
                return str(val).strip()

    return str(instance).strip()


def _portal_find_articulo_por_codigo_v1(linea):
    code = getattr(linea, "cod_articulo_legacy", None) or _portal_raw_v1(linea).get("codigo_detectado") or _portal_raw_v1(linea).get("codigo")
    if not code:
        return ""

    code_s = str(code).strip()
    team = getattr(getattr(linea, "factura", None), "team", None)

    # 1) ArticuloCompra vinculado a RecursoCatalogo legacy.
    try:
        ArticuloCompra = apps.get_model("gestion", "ArticuloCompra")
        qs = ArticuloCompra.objects.all()

        if team and "team" in [f.name for f in ArticuloCompra._meta.fields]:
            qs_team = qs.filter(team=team)
        else:
            qs_team = qs

        candidates = []

        try:
            candidates.append(qs_team.filter(recurso_catalogo__legacy_id=code_s).first())
        except Exception:
            pass

        try:
            candidates.append(qs_team.filter(recurso_catalogo__legacy_id=int(code_s)).first())
        except Exception:
            pass

        for field in ("codigo", "codigo_interno", "cod_articulo", "cod_articulo_legacy"):
            if field in [f.name for f in ArticuloCompra._meta.fields]:
                try:
                    candidates.append(qs_team.filter(**{field: code_s}).first())
                except Exception:
                    pass

        for obj in candidates:
            txt = _portal_model_text_v1(obj)
            if txt:
                return txt
    except Exception:
        pass

    # 2) RecursoCatalogo directo.
    try:
        RecursoCatalogo = apps.get_model("planificacion_obra", "RecursoCatalogo")
        qs = RecursoCatalogo.objects.all()

        if team and "team" in [f.name for f in RecursoCatalogo._meta.fields]:
            qs_team = qs.filter(team=team)
        else:
            qs_team = qs

        candidates = []

        for field in ("legacy_id", "codigo", "cod_recurso", "cod_articulo", "id"):
            if field in [f.name for f in RecursoCatalogo._meta.fields]:
                try:
                    candidates.append(qs_team.filter(**{field: code_s}).first())
                except Exception:
                    pass
                try:
                    candidates.append(qs_team.filter(**{field: int(code_s)}).first())
                except Exception:
                    pass

        for obj in candidates:
            txt = _portal_model_text_v1(obj)
            if txt:
                return txt
    except Exception:
        pass

    return ""


@register.filter(name="factura_linea_descripcion_display")
def factura_linea_descripcion_display(linea):
    # Artículo ya vinculado.
    txt = _portal_model_text_v1(getattr(linea, "articulo_compra", None))
    if txt:
        return txt

    # Texto guardado en la propia línea.
    txt = _portal_first_text_v1(linea, (
        "descripcion",
        "descripcion_detectada",
        "descripcion_articulo",
        "nombre_articulo",
        "producto",
        "concepto",
    ))
    if txt:
        return txt

    # Buscar en la línea de albarán origen.
    try:
        albaran = getattr(linea, "albaran", None)
        linea_albaran_legacy = getattr(linea, "linea_albaran_legacy", None)
        if albaran and linea_albaran_legacy:
            la = albaran.lineas.filter(linea=linea_albaran_legacy).select_related("articulo_compra").first()
            if la:
                txt = _portal_model_text_v1(getattr(la, "articulo_compra", None))
                if txt:
                    return txt

                txt = _portal_first_text_v1(la, (
                    "descripcion",
                    "descripcion_detectada",
                    "descripcion_articulo",
                    "nombre_articulo",
                    "producto",
                    "concepto",
                ))
                if txt:
                    return txt
    except Exception:
        pass

    # Resolver por código legacy contra ArticuloCompra / RecursoCatalogo.
    txt = _portal_find_articulo_por_codigo_v1(linea)
    if txt:
        return txt

    code = getattr(linea, "cod_articulo_legacy", None)
    return f"Recurso {code}" if code else "—"


def _portal_factura_iva_pct_v1(linea):
    raw = _portal_raw_v1(linea)

    for key in ("iva_porcentaje", "porcentaje_iva", "iva_pct", "tasa_iva", "tasa"):
        if raw.get(key) not in (None, ""):
            return _portal_linea_dec_v1(raw.get(key))

    factura = getattr(linea, "factura", None)
    if factura:
        fraw = _portal_raw_v1(factura)

        for key in ("iva_porcentaje", "porcentaje_iva", "iva_pct", "tasa_iva", "tasa"):
            if fraw.get(key) not in (None, ""):
                return _portal_linea_dec_v1(fraw.get(key))

        base = _portal_linea_dec_v1(getattr(factura, "importe_base_imponible", None))
        iva = _portal_linea_dec_v1(getattr(factura, "importe_iva", None))

        if base:
            return (iva / base * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return None


@register.filter(name="factura_linea_iva_display")
def factura_linea_iva_display(linea):
    raw = _portal_raw_v1(linea)

    for key in ("importe_iva_linea", "iva_importe", "iva_linea", "importe_iva"):
        if raw.get(key) not in (None, ""):
            return _portal_money_es_v1(raw.get(key))

    base = _portal_linea_dec_v1(getattr(linea, "importe_linea", None))
    pct = _portal_factura_iva_pct_v1(linea)

    if pct is None:
        return "—"

    iva = (base * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return _portal_money_es_v1(iva)


@register.filter(name="factura_linea_total_iva_display")
def factura_linea_total_iva_display(linea):
    raw = _portal_raw_v1(linea)

    for key in ("importe_total_con_iva", "total_con_iva", "total_linea_con_iva"):
        if raw.get(key) not in (None, ""):
            return _portal_money_es_v1(raw.get(key))

    base = _portal_linea_dec_v1(getattr(linea, "importe_linea", None))
    pct = _portal_factura_iva_pct_v1(linea)

    if pct is None:
        return _portal_money_es_v1(base)

    iva = (base * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (base + iva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return _portal_money_es_v1(total)



# IONOS_FACTURA_DESCRIPCION_OCR_V2
_gestion_factura_descripcion_before_ionos_v2 = (
    globals().get(
        "factura_linea_descripcion_display"
    )
)


@register.filter(
    name="factura_linea_descripcion_display"
)
def factura_linea_descripcion_display_ionos_v2(
    linea,
):
    raw = (
        linea.raw_data
        if isinstance(
            getattr(linea, "raw_data", None),
            dict,
        )
        else {}
    )

    description = (
        raw.get("descripcion_detectada")
        or raw.get("descripcion_ocr")
    )

    if description:
        return description

    if (
        _gestion_factura_descripcion_before_ionos_v2
        is not None
    ):
        return (
            _gestion_factura_descripcion_before_ionos_v2(
                linea
            )
        )

    article = getattr(
        linea,
        "articulo_compra",
        None,
    )

    return (
        getattr(article, "nombre", None)
        or getattr(
            article,
            "descripcion",
            None,
        )
        or "—"
    )


# ============================================================================
# FACTURA_LINEA_TOTAL_IVA_CANONICO_V2
# ============================================================================
#
# Fuente canónica para presentación:
#
#   total línea = importe_linea + importe_iva_linea
#
# Si no existe importe_iva_linea:
#   total línea = importe_linea + IVA calculado desde el porcentaje.
#
# Los campos históricos:
#   importe_total_con_iva
#   total_con_iva
#
# son solamente fallback.
#
# Esto evita que un valor raw obsoleto prevalezca sobre la economía
# actualmente persistida de la línea.
# ============================================================================


@register.filter(
    name="factura_linea_total_iva_display"
)
def factura_linea_total_iva_display(
    linea,
):

    raw = _portal_raw_v1(
        linea
    )


    ###########################################################################
    # BASE CANÓNICA: campo real del modelo.
    ###########################################################################

    base = _portal_linea_dec_v1(
        getattr(
            linea,
            "importe_linea",
            None,
        )
    )


    ###########################################################################
    # 1. Si existe importe IVA de línea, es la fuente preferente.
    ###########################################################################

    iva_raw = None

    for key in (
        "importe_iva_linea",
        "iva_importe",
        "iva_linea",
        "importe_iva",
    ):

        if raw.get(key) not in (
            None,
            "",
        ):

            iva_raw = raw.get(
                key
            )

            break


    if iva_raw not in (
        None,
        "",
    ):

        iva = (
            _portal_linea_dec_v1(
                iva_raw
            )
            .quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        )


        total = (
            base
            + iva
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


        return _portal_money_es_v1(
            total
        )


    ###########################################################################
    # 2. Si no existe importe IVA, calcular desde porcentaje.
    ###########################################################################

    pct = (
        _portal_factura_iva_pct_v1(
            linea
        )
    )


    if pct is not None:

        iva = (
            base
            * pct
            / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


        total = (
            base
            + iva
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


        return _portal_money_es_v1(
            total
        )


    ###########################################################################
    # 3. Compatibilidad histórica.
    #
    # Preferir primero el nombre canónico más reciente.
    ###########################################################################

    for key in (
        "total_linea_con_iva",
        "importe_total_con_iva",
        "total_con_iva",
        "importe_tti",
        "importe_total",
        "total_tti",
    ):

        if raw.get(key) not in (
            None,
            "",
        ):

            return _portal_money_es_v1(
                raw.get(key)
            )


    ###########################################################################
    # Sin IVA conocido: al menos la base real.
    ###########################################################################

    return _portal_money_es_v1(
        base
    )

