from __future__ import annotations

from decimal import Decimal, InvalidOperation

from actividad.models import ActividadPlataforma
from actividad.services import registrar_actividad


TIPOS_DOCUMENTO = {
    "albaran": {
        "label": "albarán",
        "code_field": "cod_albaran",
        "external_field": (
            "num_albaran_proveedor"
        ),
        "amount_field": "importe_albaran",
        "url_prefix": (
            "/app/gestion/albaranes"
        ),
        "action": "crear_albaran",
    },
    "factura": {
        "label": "factura",
        "code_field": "cod_factura",
        "external_field": (
            "num_factura_proveedor"
        ),
        "amount_field": "importe_factura",
        "url_prefix": (
            "/app/gestion/facturas"
        ),
        "action": "crear_factura",
    },
}


def _proveedor_nombre(documento) -> str:
    proveedor = getattr(
        documento,
        "proveedor",
        None,
    )

    if proveedor is None:
        return ""

    return str(
        getattr(
            proveedor,
            "nombre_comercial",
            "",
        )
        or getattr(
            proveedor,
            "nombre_fiscal",
            "",
        )
        or proveedor
    ).strip()


def _importe_decimal(value):
    try:
        return Decimal(
            str(value or "0")
        ).quantize(
            Decimal("0.01")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal("0.00")


def _importe_es(value) -> str:
    amount = _importe_decimal(value)

    text = f"{amount:,.2f}"

    return (
        text
        .replace(",", "__MILES__")
        .replace(".", ",")
        .replace("__MILES__", ".")
    )


def _raw_data(documento) -> dict:
    value = getattr(
        documento,
        "raw_data",
        None,
    )

    return value if isinstance(value, dict) else {}


def _resolver_flujo(
    documento,
    origen_flujo=None,
):
    if origen_flujo:
        return str(
            origen_flujo
        ).strip().lower()

    raw = _raw_data(documento)

    source = str(
        raw.get("source") or ""
    ).strip().lower()

    created_from = str(
        raw.get("created_from") or ""
    ).strip().lower()

    if "desde_albaran" in created_from:
        return "desde_albaranes"

    if (
        "pdf" in source
        or "ocr" in source
        or "pdf" in created_from
        or "ocr" in created_from
    ):
        return "pdf_ocr"

    return "manual"


def _descripcion_flujo(
    flujo,
    albaranes_count,
):
    if flujo == "pdf_ocr":
        return " mediante PDF/OCR"

    if flujo == "desde_albaranes":
        if albaranes_count == 1:
            return " desde 1 albarán"

        return (
            f" desde {albaranes_count} "
            "albaranes"
        )

    return ""


def registrar_alta_documento_gestion(
    *,
    documento,
    actor,
    tipo,
    origen_flujo=None,
    albaranes=None,
    tiene_adjunto=None,
    diferir_hasta_commit=True,
):
    """
    Registra una única actividad por alta funcional.

    No debe invocarse desde imports, sincronizaciones
    técnicas, señales generales ni administración.
    """
    tipo = str(tipo or "").strip().lower()

    if tipo not in TIPOS_DOCUMENTO:
        raise ValueError(
            "Tipo documental de Gestión no válido."
        )

    document_id = getattr(
        documento,
        "pk",
        None,
    )

    if not document_id:
        raise ValueError(
            "El documento debe estar guardado."
        )

    config = TIPOS_DOCUMENTO[tipo]

    team = getattr(
        documento,
        "team",
        None,
    )

    if team is None:
        raise ValueError(
            "El documento no tiene empresa."
        )

    code = str(
        getattr(
            documento,
            config["code_field"],
            "",
        )
        or ""
    ).strip()

    external_number = str(
        getattr(
            documento,
            config["external_field"],
            "",
        )
        or ""
    ).strip()

    amount = getattr(
        documento,
        config["amount_field"],
        None,
    )

    provider_name = _proveedor_nombre(
        documento
    )

    raw = _raw_data(documento)
    flow = _resolver_flujo(
        documento,
        origen_flujo,
    )

    albaranes = list(albaranes or [])

    albaran_ids = [
        item.pk
        for item in albaranes
        if getattr(item, "pk", None)
    ]

    albaran_codes = [
        str(
            getattr(
                item,
                "cod_albaran",
                "",
            )
            or ""
        ).strip()
        for item in albaranes
        if str(
            getattr(
                item,
                "cod_albaran",
                "",
            )
            or ""
        ).strip()
    ]

    label = config["label"]

    document_repr = (
        f"{label.capitalize()} {code}"
        if code
        else f"{label.capitalize()} #{document_id}"
    )

    if external_number:
        document_repr += (
            f" · {external_number}"
        )

    description = (
        f"ha creado el {label} "
        f"{code or f'#{document_id}'}"
    )

    if external_number:
        description += (
            f" · {external_number}"
        )

    if provider_name:
        description += (
            f" de {provider_name}"
        )

    description += (
        f" por {_importe_es(amount)} €"
    )

    description += _descripcion_flujo(
        flow,
        len(albaran_ids),
    )

    description += "."

    metadata = {
        "tipo_documento": tipo,
        "documento_id": document_id,
        "codigo_interno": code,
        "numero_proveedor": external_number,
        "proveedor_id": getattr(
            documento,
            "proveedor_id",
            None,
        ),
        "proveedor": provider_name,
        "importe": str(
            _importe_decimal(amount)
        ),
        "flujo": flow,
        "source": raw.get("source"),
        "created_from": raw.get(
            "created_from"
        ),
        "origen_alta": str(
            getattr(
                documento,
                "origen_alta",
                "",
            )
            or ""
        ),
        "ambito_gestion": str(
            getattr(
                documento,
                "ambito_gestion",
                "",
            )
            or ""
        ),
        "tiene_adjunto": (
            bool(tiene_adjunto)
            if tiene_adjunto is not None
            else None
        ),
        "albaran_ids": albaran_ids,
        "albaran_codigos": albaran_codes,
        "albaranes_count": len(
            albaran_ids
        ),
    }

    return registrar_actividad(
        modulo="gestion",
        accion=config["action"],
        actor=actor,
        team=team,
        objeto=documento,
        objeto_repr=document_repr,
        descripcion=description,
        url=(
            f"{config['url_prefix']}/"
            f"{document_id}/"
        ),
        visibilidad=(
            ActividadPlataforma
            .Visibilidad
            .EQUIPO
        ),
        origen=(
            ActividadPlataforma
            .Origen
            .EXPLICITO
        ),
        metadata=metadata,
        agrupacion_key=(
            f"gestion:alta:{tipo}:"
            f"{team.pk}:"
            f"{getattr(actor, 'pk', '')}"
        ),
        clave_idempotencia=(
            f"gestion:alta:{tipo}:"
            f"{document_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )
