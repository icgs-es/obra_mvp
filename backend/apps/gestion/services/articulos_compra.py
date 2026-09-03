import re
import unicodedata
from decimal import Decimal


def normalizar_nombre_articulo(descripcion):
    value = (descripcion or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value[:255] or "Artículo sin descripción"


def normalizar_clave_articulo(value):
    """Clave estricta para detectar equivalencias tipográficas.

    Separa letras y números para que ``M-5``, ``M5`` y ``M 5`` sean la
    misma referencia, pero conserva todos los demás tokens. De este modo no
    se confunden morteros con composiciones, formatos o resistencias distintas.
    """
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.upper()
    value = re.sub(r"(?<=[A-Z])(?=[0-9])|(?<=[0-9])(?=[A-Z])", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())


def buscar_articulo_equivalente(
    *,
    ArticuloCompra,
    RecursoCatalogo,
    team_ids,
    nombre,
    proveedor=None,
):
    """Resuelve un artículo existente por equivalencia normalizada exacta.

    El resultado queda limitado a los teams recibidos. Se prefiere un alias
    del proveedor, después el team solicitado y finalmente el PK más antiguo.
    No realiza coincidencias parciales.
    """
    clave = normalizar_clave_articulo(nombre)
    team_ids = [int(team_id) for team_id in team_ids if team_id]
    if not clave or not team_ids:
        return None, None

    articulos = list(
        ArticuloCompra.objects
        .filter(team_id__in=team_ids, activo=True)
        .order_by("team_id", "id")
    )
    if not articulos:
        return None, None

    articulo_ids = [art.id for art in articulos]
    recurso_ids = {
        art.recurso_catalogo_id
        for art in articulos
        if art.recurso_catalogo_id
    }
    recursos = RecursoCatalogo.objects.in_bulk(recurso_ids)

    from django.apps import apps
    ArticuloProveedorAlias = apps.get_model(
        "gestion",
        "ArticuloProveedorAlias",
    )
    aliases_qs = ArticuloProveedorAlias.objects.filter(
        articulo_id__in=articulo_ids,
        estado=ArticuloProveedorAlias.ESTADO_VINCULADO,
    )
    if proveedor is not None:
        aliases_qs = aliases_qs.filter(proveedor=proveedor)
    aliases = list(aliases_qs.order_by("id"))
    aliases_by_article = {}
    for alias in aliases:
        aliases_by_article.setdefault(alias.articulo_id, []).append(alias)

    matches = []
    for art in articulos:
        recurso = recursos.get(art.recurso_catalogo_id)
        article_aliases = aliases_by_article.get(art.id, [])
        values = [art.nombre, art.descripcion]
        if recurso:
            values.extend([recurso.nombre, recurso.observaciones])
        for alias in article_aliases:
            values.extend([
                alias.codigo_proveedor,
                alias.descripcion_proveedor,
            ])

        if not any(normalizar_clave_articulo(value) == clave for value in values):
            continue

        provider_rank = 0 if article_aliases else 1
        team_rank = team_ids.index(art.team_id) if art.team_id in team_ids else len(team_ids)
        matches.append((provider_rank, team_rank, art.id, art, article_aliases))

    if not matches:
        return None, None

    _provider_rank, _team_rank, _id, articulo, article_aliases = min(matches)
    return articulo, (article_aliases[0] if article_aliases else None)


def _codigo_int(value):
    raw = (value or "").strip()
    if not re.fullmatch(r"\d+", raw):
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _next_recurso_legacy_id(RecursoCatalogo, team):
    last = (
        RecursoCatalogo.objects
        .filter(team=team)
        .order_by("-legacy_id")
        .values_list("legacy_id", flat=True)
        .first()
    )
    return (last or 0) + 1


def _find_recurso_catalogo(*, RecursoCatalogo, team, codigo, descripcion):
    """
    Resolución conservadora:
    1) Si el código OCR es numérico y existe como legacy_id en RecursoCatalogo, se reutiliza.
    2) Si no, se intenta match exacto por nombre normalizado.
    3) Si no existe, se creará un recurso nuevo en confirmación humana.
    """
    codigo_num = _codigo_int(codigo)
    if codigo_num is not None:
        recurso = (
            RecursoCatalogo.objects
            .filter(team=team, legacy_id=codigo_num)
            .first()
        )
        if recurso:
            return recurso, False, "legacy_id_match"

    nombre = normalizar_nombre_articulo(descripcion or codigo)
    recurso = (
        RecursoCatalogo.objects
        .filter(team=team, nombre__iexact=nombre)
        .first()
    )
    if recurso:
        return recurso, False, "nombre_exact_match"

    return None, False, "not_found"


def _create_recurso_catalogo(*, RecursoCatalogo, team, codigo, descripcion, unidad, precio):
    nombre = normalizar_nombre_articulo(descripcion or codigo)
    legacy_id = _next_recurso_legacy_id(RecursoCatalogo, team)

    recurso = RecursoCatalogo.objects.create(
        team=team,
        legacy_id=legacy_id,
        nombre=nombre,
        tipo="MATERIAL",
        unidad=unidad or "",
        stock=None,
        ultimo_precio_unidad=precio,
        precio_unidad_uso=precio,
        control_stock=False,
        observaciones="Creado automáticamente desde OCR de compras. Revisar antes de usar en stock/obra.",
        raw_data={
            "source": "portal_pdf_ocr",
            "created_from": "get_or_create_articulo_alias_desde_ocr",
            "codigo_detectado": codigo,
            "descripcion_detectada": descripcion,
            "stock_pendiente_revision": True,
        },
    )
    return recurso


def _get_or_create_articulo_compra(*, ArticuloCompra, team, recurso, codigo, descripcion, unidad):
    """
    ArticuloCompra queda como puente operativo.
    Si ya existe por recurso_catalogo_id, se reutiliza.
    Si no, se reutiliza/crea por team+nombre.
    """
    articulo = (
        ArticuloCompra.objects
        .filter(team=team, recurso_catalogo_id=recurso.id)
        .first()
    )
    if articulo:
        return articulo, False

    nombre = normalizar_nombre_articulo(recurso.nombre or descripcion or codigo)

    articulo, created = ArticuloCompra.objects.get_or_create(
        team=team,
        nombre=nombre,
        defaults={
            "descripcion": descripcion or recurso.observaciones or "",
            "unidad": unidad or recurso.unidad or "",
            "tipo": recurso.tipo or "MATERIAL",
            "recurso_catalogo_id": recurso.id,
            "raw_data": {
                "source": "portal_pdf_ocr",
                "created_from": "get_or_create_articulo_alias_desde_ocr",
                "recurso_catalogo_id": recurso.id,
                "recurso_legacy_id": recurso.legacy_id,
                "codigo_detectado": codigo,
            },
        },
    )

    changed = False
    raw = articulo.raw_data or {}

    if articulo.recurso_catalogo_id != recurso.id:
        articulo.recurso_catalogo_id = recurso.id
        changed = True

    if unidad and not articulo.unidad:
        articulo.unidad = unidad
        changed = True

    raw.update({
        "recurso_catalogo_id": recurso.id,
        "recurso_legacy_id": recurso.legacy_id,
        "last_ocr_codigo_detectado": codigo,
    })
    articulo.raw_data = raw
    changed = True

    if changed:
        articulo.save(update_fields=["recurso_catalogo_id", "unidad", "raw_data", "actualizado_en"])

    return articulo, created


def get_or_create_articulo_alias_desde_ocr(*, team, proveedor, codigo, descripcion, unidad="", precio=None, fecha=None):
    """
    Flujo actualizado:
    OCR -> RecursoCatalogo -> ArticuloCompra -> ArticuloProveedorAlias -> línea

    Mantiene firma compatible con las vistas existentes:
    return articulo, alias, articulo_created, alias_created

    Además añade atributos transitorios al artículo para trazabilidad en raw_data de línea:
    - _ocr_recurso_catalogo_id
    - _ocr_recurso_legacy_id
    - _ocr_recurso_created
    - _ocr_recurso_match_source
    """
    from django.apps import apps

    ArticuloCompra = apps.get_model("gestion", "ArticuloCompra")
    ArticuloProveedorAlias = apps.get_model("gestion", "ArticuloProveedorAlias")
    RecursoCatalogo = apps.get_model("planificacion_obra", "RecursoCatalogo")

    codigo = (codigo or "").strip()[:120]
    descripcion = (descripcion or "").strip()[:500]
    unidad = (unidad or "").strip()[:40]

    if precio is not None and not isinstance(precio, Decimal):
        try:
            precio = Decimal(str(precio))
        except Exception:
            precio = None

    if not codigo:
        codigo = "SIN-CODIGO"

    # 1) Si ya existe alias proveedor, reutilizarlo.
    alias = None
    if proveedor is not None:
        alias = (
            ArticuloProveedorAlias.objects
            .filter(team=team, proveedor=proveedor, codigo_proveedor=codigo)
            .select_related("articulo")
            .first()
        )

    if alias:
        articulo = alias.articulo
        recurso = None
        recurso_created = False
        match_source = "alias_existente"

        if not articulo.recurso_catalogo_id:
            recurso, _, match_source = _find_recurso_catalogo(
                RecursoCatalogo=RecursoCatalogo,
                team=team,
                codigo=codigo,
                descripcion=descripcion or articulo.nombre,
            )

            if recurso is None:
                recurso = _create_recurso_catalogo(
                    RecursoCatalogo=RecursoCatalogo,
                    team=team,
                    codigo=codigo,
                    descripcion=descripcion or articulo.nombre,
                    unidad=unidad or articulo.unidad,
                    precio=precio,
                )
                recurso_created = True
                match_source = "created_from_existing_alias_ocr"

            articulo.recurso_catalogo_id = recurso.id
            raw = articulo.raw_data or {}
            raw.update({
                "recurso_catalogo_id": recurso.id,
                "recurso_legacy_id": recurso.legacy_id,
                "linked_from": "ocr_alias_existing",
                "match_source": match_source,
                "stock_pendiente_revision": True,
            })
            articulo.raw_data = raw
            articulo.save(update_fields=["recurso_catalogo_id", "raw_data", "actualizado_en"])

        elif articulo.recurso_catalogo_id:
            recurso = RecursoCatalogo.objects.filter(id=articulo.recurso_catalogo_id).first()

        changed = False
        if descripcion and not alias.descripcion_proveedor:
            alias.descripcion_proveedor = descripcion
            changed = True
        if precio is not None:
            alias.ultimo_precio = precio
            changed = True
        if fecha is not None:
            alias.ultima_fecha = fecha
            changed = True
        if changed:
            alias.save(update_fields=["descripcion_proveedor", "ultimo_precio", "ultima_fecha", "actualizado_en"])

        articulo._ocr_recurso_catalogo_id = recurso.id if recurso else articulo.recurso_catalogo_id
        articulo._ocr_recurso_legacy_id = recurso.legacy_id if recurso else None
        articulo._ocr_recurso_created = recurso_created
        articulo._ocr_recurso_match_source = match_source
        return articulo, alias, False, False

    # 2) Antes de crear, resolver equivalencias tipográficas exactas dentro
    # del team (p. ej. M-5, M5 y M 5). Esto protege tanto OCR como altas
    # manuales frente a duplicados de un recurso ya enlazado.
    articulo_existente, _alias_equivalente = buscar_articulo_equivalente(
        ArticuloCompra=ArticuloCompra,
        RecursoCatalogo=RecursoCatalogo,
        team_ids=[team.id],
        nombre=descripcion or codigo,
        proveedor=proveedor,
    )
    if articulo_existente and articulo_existente.recurso_catalogo_id:
        recurso = RecursoCatalogo.objects.filter(
            id=articulo_existente.recurso_catalogo_id,
        ).first()
        if recurso:
            alias_created = False
            if proveedor is not None:
                alias = _alias_equivalente
                if alias is None:
                    alias = ArticuloProveedorAlias.objects.create(
                        team=team,
                        proveedor=proveedor,
                        articulo=articulo_existente,
                        codigo_proveedor=codigo,
                        descripcion_proveedor=descripcion,
                        unidad_proveedor=unidad,
                        estado="VINCULADO",
                        ultimo_precio=precio,
                        ultima_fecha=fecha,
                        raw_data={
                            "source": "portal_pdf_ocr",
                            "created_from": "get_or_create_articulo_alias_desde_ocr",
                            "recurso_catalogo_id": recurso.id,
                            "recurso_legacy_id": recurso.legacy_id,
                            "match_source": "normalized_existing_article",
                        },
                    )
                    alias_created = True
                else:
                    changed_fields = []
                    if precio is not None:
                        alias.ultimo_precio = precio
                        changed_fields.append("ultimo_precio")
                    if fecha is not None:
                        alias.ultima_fecha = fecha
                        changed_fields.append("ultima_fecha")
                    if changed_fields:
                        alias.save(update_fields=changed_fields + ["actualizado_en"])

            articulo_existente._ocr_recurso_catalogo_id = recurso.id
            articulo_existente._ocr_recurso_legacy_id = recurso.legacy_id
            articulo_existente._ocr_recurso_created = False
            articulo_existente._ocr_recurso_match_source = (
                "normalized_existing_article"
            )
            return (
                articulo_existente,
                alias,
                False,
                alias_created,
            )

    # 3) Resolver o crear RecursoCatalogo.
    recurso, recurso_created, match_source = _find_recurso_catalogo(
        RecursoCatalogo=RecursoCatalogo,
        team=team,
        codigo=codigo,
        descripcion=descripcion,
    )

    if recurso is None:
        recurso = _create_recurso_catalogo(
            RecursoCatalogo=RecursoCatalogo,
            team=team,
            codigo=codigo,
            descripcion=descripcion,
            unidad=unidad,
            precio=precio,
        )
        recurso_created = True
        match_source = "created_from_ocr"

    # Actualizar precio reciente del recurso, sin tocar stock.
    changed_recurso = False
    if precio is not None:
        recurso.ultimo_precio_unidad = precio
        recurso.precio_unidad_uso = precio
        changed_recurso = True
    if unidad and not recurso.unidad:
        recurso.unidad = unidad
        changed_recurso = True
    if changed_recurso:
        recurso.save(update_fields=["ultimo_precio_unidad", "precio_unidad_uso", "unidad", "actualizado_en"])

    # 4) Resolver ArticuloCompra como puente.
    articulo, articulo_created = _get_or_create_articulo_compra(
        ArticuloCompra=ArticuloCompra,
        team=team,
        recurso=recurso,
        codigo=codigo,
        descripcion=descripcion,
        unidad=unidad,
    )

    # 5) Crear alias proveedor solo si hay proveedor.
    alias_created = False
    if proveedor is not None:
        alias = ArticuloProveedorAlias.objects.create(
            team=team,
            proveedor=proveedor,
            articulo=articulo,
            codigo_proveedor=codigo,
            descripcion_proveedor=descripcion,
            unidad_proveedor=unidad,
            estado="VINCULADO",
            ultimo_precio=precio,
            ultima_fecha=fecha,
            raw_data={
                "source": "portal_pdf_ocr",
                "created_from": "get_or_create_articulo_alias_desde_ocr",
                "recurso_catalogo_id": recurso.id,
                "recurso_legacy_id": recurso.legacy_id,
                "match_source": match_source,
            },
        )
        alias_created = True

    articulo._ocr_recurso_catalogo_id = recurso.id
    articulo._ocr_recurso_legacy_id = recurso.legacy_id
    articulo._ocr_recurso_created = recurso_created
    articulo._ocr_recurso_match_source = match_source

    return articulo, alias, articulo_created, alias_created
