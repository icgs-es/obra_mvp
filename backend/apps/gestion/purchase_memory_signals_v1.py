"""
PORTAL INTASA · Signals de memoria de compra V1A.

Toda línea nueva o editada normaliza sus alias de unidad.
Solo las compras positivas actualizan memoria de precio.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import (
    FacturaProveedorLineaGestion,
    AlbaranProveedorLineaGestion,
)
from .purchase_memory_v1 import (
    remember_purchase_from_line,
)
from .unit_catalog_v1 import (
    normalize_unit,
)


logger = logging.getLogger(
    __name__
)


def _normalize_line_units(
    instance,
):
    updates = {}

    if hasattr(
        instance,
        "unidad_compra",
    ):
        current = str(
            getattr(
                instance,
                "unidad_compra",
                "",
            )
            or ""
        ).strip()

        normalized = normalize_unit(
            current
        )

        if (
            normalized
            and normalized != current
        ):
            updates[
                "unidad_compra"
            ] = normalized

            instance.unidad_compra = (
                normalized
            )

    if hasattr(
        instance,
        "unidad",
    ):
        current = str(
            getattr(
                instance,
                "unidad",
                "",
            )
            or ""
        ).strip()

        normalized = normalize_unit(
            current
        )

        if (
            normalized
            and normalized != current
        ):
            updates[
                "unidad"
            ] = normalized

            instance.unidad = normalized

    if updates:
        instance.__class__.objects.filter(
            pk=instance.pk
        ).update(
            **updates
        )

    return updates


def _remember(instance):
    try:
        normalized = _normalize_line_units(
            instance
        )

        result = remember_purchase_from_line(
            instance
        )

        logger.debug(
            "Compra V1A %s#%s normalizada=%s memoria=%s",
            instance.__class__.__name__,
            instance.pk,
            normalized,
            result,
        )

    except Exception:
        logger.exception(
            "No se pudo procesar la unidad o memoria "
            "de compra para %s#%s",
            instance.__class__.__name__,
            instance.pk,
        )


@receiver(
    post_save,
    sender=FacturaProveedorLineaGestion,
    dispatch_uid=(
        "gestion_purchase_memory_v1_"
        "factura_linea"
    ),
)
def factura_linea_purchase_memory(
    sender,
    instance,
    **kwargs,
):
    _remember(
        instance
    )


@receiver(
    post_save,
    sender=AlbaranProveedorLineaGestion,
    dispatch_uid=(
        "gestion_purchase_memory_v1_"
        "albaran_linea"
    ),
)
def albaran_linea_purchase_memory(
    sender,
    instance,
    **kwargs,
):
    _remember(
        instance
    )
