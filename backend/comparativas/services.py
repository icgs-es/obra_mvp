import hashlib
from pathlib import Path

from django.db import transaction
from django.db.models import Max

from .models import (
    Comparativa,
    DocumentoComparativa,
    Oferta,
    Ofertante,
)


@transaction.atomic
def crear_oferta(
    *,
    ofertante,
    cleaned_data,
    user,
):
    locked = (
        Ofertante.objects
        .select_for_update()
        .select_related("comparativa")
        .get(pk=ofertante.pk)
    )

    ultimo = (
        locked.ofertas
        .aggregate(max_version=Max("version"))
        ["max_version"]
        or 0
    )

    oferta = Oferta.objects.create(
        ofertante=locked,
        version=ultimo + 1,
        fecha_documento=cleaned_data.get(
            "fecha_documento"
        ),
        referencia=cleaned_data.get(
            "referencia",
            "",
        ),
        base=cleaned_data.get("base"),
        impuestos=cleaned_data.get(
            "impuestos"
        ),
        total=cleaned_data.get("total"),
        observaciones=cleaned_data.get(
            "observaciones",
            "",
        ),
        creado_por=user,
    )

    comparativa = locked.comparativa

    if (
        comparativa.estado
        == Comparativa.Estado.BORRADOR
    ):
        comparativa.estado = (
            Comparativa.Estado.EN_COMPARACION
        )
        comparativa.save(
            update_fields=(
                "estado",
                "updated_at",
            )
        )

    return oferta


def _sha256_uploaded_file(uploaded_file):
    digest = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        digest.update(chunk)

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    return digest.hexdigest()


@transaction.atomic
def guardar_documento(
    *,
    oferta,
    uploaded_file,
    user,
):
    sha256 = _sha256_uploaded_file(
        uploaded_file
    )

    existente = (
        DocumentoComparativa.objects
        .filter(
            oferta=oferta,
            sha256=sha256,
        )
        .first()
    )

    if existente:
        return existente, False

    extension = Path(
        uploaded_file.name or ""
    ).suffix.lower()

    documento = (
        DocumentoComparativa.objects.create(
            oferta=oferta,
            archivo=uploaded_file,
            nombre_original=(
                uploaded_file.name
                or "documento"
            ),
            extension=extension,
            content_type=getattr(
                uploaded_file,
                "content_type",
                "",
            )
            or "",
            tamano_bytes=uploaded_file.size,
            sha256=sha256,
            estado_analisis=(
                DocumentoComparativa
                .EstadoAnalisis
                .PENDIENTE
            ),
            subido_por=user,
        )
    )

    return documento, True
