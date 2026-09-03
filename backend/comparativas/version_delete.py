import logging

from django.db import transaction

from .models import (
    DocumentoComparativa,
    Oferta,
)


logger = logging.getLogger(__name__)


def _delete_unreferenced_document_files(
    file_refs,
):
    """
    Elimina del storage únicamente archivos que ya no
    estén referenciados por ningún DocumentoComparativa.

    Se ejecuta mediante transaction.on_commit(): nunca
    se borra el fichero antes de confirmar el COMMIT BD.
    """

    for storage, name in file_refs:
        if not name:
            continue

        if (
            DocumentoComparativa.objects
            .filter(archivo=name)
            .exists()
        ):
            logger.warning(
                "comparativas_version_delete_file_preserved "
                "file=%s reason=still_referenced",
                name,
            )
            continue

        try:
            storage.delete(name)

        except Exception:
            # La eliminación del negocio ya hizo COMMIT.
            # Un error de storage debe quedar registrado,
            # no provocar inconsistencias transaccionales.
            logger.exception(
                "comparativas_version_delete_file_cleanup_failed "
                "file=%s",
                name,
            )


@transaction.atomic
def delete_offer_version(
    *,
    oferta,
    user,
):
    """
    Elimina exclusivamente una Oferta/version.

    Conserva:
      - Ofertante.
      - Comparativa.
      - restantes versiones del ofertante.

    CASCADE elimina:
      - DocumentoComparativa de esa Oferta.
      - ConceptoOferta de esa Oferta.

    Los archivos físicos se eliminan después del COMMIT
    y solo cuando ninguna otra fila los referencia.
    """

    locked = (
        Oferta.objects
        .select_for_update()
        .select_related(
            "ofertante__comparativa"
        )
        .get(pk=oferta.pk)
    )

    documentos = list(
        DocumentoComparativa.objects
        .select_for_update()
        .filter(oferta=locked)
        .order_by("pk")
    )

    file_refs = []

    for documento in documentos:
        if documento.archivo:
            file_refs.append(
                (
                    documento.archivo.storage,
                    documento.archivo.name,
                )
            )

    result = {
        "offer_id": locked.pk,
        "version": locked.version,
        "ofertante_id": locked.ofertante_id,
        "ofertante_nombre": locked.ofertante.nombre,
        "comparativa_uuid": str(
            locked.ofertante.comparativa.uuid
        ),
        "documentos": len(documentos),
        "conceptos": locked.conceptos.count(),
    }

    logger.info(
        (
            "comparativas_offer_version_delete "
            "offer_id=%s version=%s ofertante_id=%s "
            "user_id=%s documentos=%s conceptos=%s"
        ),
        result["offer_id"],
        result["version"],
        result["ofertante_id"],
        getattr(user, "pk", None),
        result["documentos"],
        result["conceptos"],
    )

    locked.delete()

    transaction.on_commit(
        lambda refs=tuple(file_refs):
            _delete_unreferenced_document_files(
                refs
            )
    )

    return result
