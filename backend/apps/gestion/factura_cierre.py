from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from apps.gestion.models import (
    FacturaProveedorGestion,
    FacturaVencimientoGestion,
)


# =============================================================================
# PORTAL INTASA
# FACTURA PAGADA · CIERRE ECONOMICO V2
#
# El texto estado="PAGADA" NO es suficiente para cerrar una factura.
#
# Evidencia económica real:
#
# - importe_pagado distinto de 0;
# - fecha_real_pago informada;
# - al menos un vencimiento realmente PAGADO.
#
# factura_update NO se bloquea nunca por esta guarda:
# el usuario debe poder corregir una factura marcada/pagada por error.
# =============================================================================


# =============================================================================
# FACTURA_PAGO_REAL_DOCUMENTAL_EDITABLE_V3
#
# El pago real cierra la dimensión financiera, no la documental.
#
# Estas operaciones pueden ejecutarse después del pago:
# - crear línea;
# - editar línea;
# - importar OCR;
# - importar desde albarán.
#
# Las vistas originales siguen aplicando login, Team, permisos,
# validaciones, duplicados y demás reglas de negocio.
# =============================================================================

RUTAS_DOCUMENTALES_EDITABLES_CON_PAGO_REAL = {
    "factura_linea_create",
    "factura_linea_update",
    "factura_lineas_desde_ocr",
    "factura_importar_desde_albaran",
}


RUTAS_CERRADAS = {
    "factura_delete": ("pk", False),

    "factura_linea_delete": ("factura_id", False),

    "factura_recalcular_desde_lineas": ("pk", False),

    "factura_lineas_a_almacen": ("pk", False),
    "factura_lineas_a_partida": ("pk", False),

    "factura_adjunto_upload": ("pk", False),
    "factura_adjunto_delete": ("factura_id", False),

    "factura_albaran_desvincular": ("factura_id", False),

    # El plan puede consultarse.
    # Una modificación POST queda bloqueada cuando ya existe pago real.
    "factura_plan_pagos": ("pk", True),

    # No se admite registrar otro pago sobre una factura con pago real.
    "factura_vencimiento_marcar_pagado": ("pk", True),
}


def _factura_decimal_no_cero_v2(value):
    try:
        return Decimal(str(value or "0")) != Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return False


def factura_tiene_pago_real(factura):
    """
    Determina si existe evidencia económica real de pago.

    No usa estado == PAGADA como prueba suficiente.
    """

    if factura is None:
        return False

    if _factura_decimal_no_cero_v2(
        getattr(
            factura,
            "importe_pagado",
            None,
        )
    ):
        return True

    if getattr(
        factura,
        "fecha_real_pago",
        None,
    ) is not None:
        return True

    try:
        manager = factura.vencimientos_pago

        if manager.filter(
            estado=FacturaVencimientoGestion.ESTADO_PAGADO
        ).exists():
            return True

    except Exception:
        pass

    return False


def factura_esta_cerrada(factura):
    """
    Compatibilidad con el nombre histórico.

    V2:
    cerrada significa "con evidencia real de pago",
    no meramente estado textual PAGADA.
    """
    return factura_tiene_pago_real(
        factura
    )


def crear_guarda(
    view,
    factura_kwarg,
    solo_post=False,
):
    @wraps(view)
    def protegida(
        request,
        *args,
        **kwargs,
    ):
        # El decorador original conserva login y permisos.
        if not getattr(
            request.user,
            "is_authenticated",
            False,
        ):
            return view(
                request,
                *args,
                **kwargs,
            )

        if (
            solo_post
            and request.method != "POST"
        ):
            return view(
                request,
                *args,
                **kwargs,
            )

        factura_id = kwargs.get(
            factura_kwarg
        )

        factura = (
            FacturaProveedorGestion.objects
            .filter(
                pk=factura_id
            )
            .only(
                "id",
                "estado",
                "importe_pagado",
                "fecha_real_pago",
            )
            .first()
        )

        if (
            factura is not None
            and factura_esta_cerrada(
                factura
            )
        ):
            messages.error(
                request,
                (
                    "La factura tiene un pago real registrado. "
                    "Las operaciones que modifican su contenido "
                    "económico están protegidas. "
                    "Puedes usar Editar para corregir la cabecera "
                    "o revisar el estado del pago."
                ),
            )

            return redirect(
                (
                    "/app/gestion/facturas/"
                    f"{factura.pk}/"
                )
            )

        return view(
            request,
            *args,
            **kwargs,
        )

    protegida._factura_pagada_cerrada_v1 = True
    protegida._factura_pagada_solo_post_v1 = solo_post
    protegida._factura_pago_real_guard_v2 = True

    return protegida


def instalar_guardas(
    views_module,
):
    aplicadas = []

    for (
        nombre,
        (
            kwarg,
            solo_post,
        ),
    ) in RUTAS_CERRADAS.items():

        view = getattr(
            views_module,
            nombre,
            None,
        )

        if view is None:
            raise RuntimeError(
                (
                    "Vista requerida "
                    f"no encontrada: {nombre}"
                )
            )

        if not getattr(
            view,
            "_factura_pago_real_guard_v2",
            False,
        ):
            setattr(
                views_module,
                nombre,
                crear_guarda(
                    view,
                    kwarg,
                    solo_post=solo_post,
                ),
            )

        aplicadas.append(
            nombre
        )

    return aplicadas
