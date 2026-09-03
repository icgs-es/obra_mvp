"""
Integración PORTAL INTASA.

La lógica de negocio de comparativas no importa directamente
Gestión ni Planificación. Las dependencias específicas del cliente
quedan concentradas aquí para facilitar la futura extracción a ORDIX.
"""


def get_team_scope(request):
    from apps.gestion.views import (
        get_current_team_scope,
    )

    return get_current_team_scope(request)


def get_obras_options(team_scope):
    from planificacion_obra.models import (
        ObraPlanificacion,
    )

    qs = (
        ObraPlanificacion.objects
        .filter(team__in=team_scope)
        .select_related("team")
        .order_by(
            "team__name",
            "legacy_cod_obra",
            "nombre",
        )
    )

    result = []

    for obra in qs:
        result.append({
            "id": obra.pk,
            "team_id": obra.team_id,
            "label": (
                f"{obra.team.name} · "
                f"{obra.codigo} · {obra.nombre}"
            ),
            "codigo": obra.codigo,
            "nombre": obra.nombre,
        })

    return result


def resolve_obra(team_scope, obra_id):
    from planificacion_obra.models import (
        ObraPlanificacion,
    )

    try:
        obra_id = int(obra_id)
    except (TypeError, ValueError):
        return None

    obra = (
        ObraPlanificacion.objects
        .select_related("team")
        .filter(
            pk=obra_id,
            team__in=team_scope,
        )
        .first()
    )

    if not obra:
        return None

    return {
        "id": obra.pk,
        "team_id": obra.team_id,
        "codigo": obra.codigo,
        "nombre": obra.nombre,
        "label": (
            f"{obra.team.name} · "
            f"{obra.codigo} · {obra.nombre}"
        ),
    }


def get_proveedores_options(
    team_scope,
    preferred_team_id=None,
):
    from apps.gestion.models import Proveedor

    qs = (
        Proveedor.objects
        .filter(
            team__in=team_scope,
            activo=True,
        )
        .select_related("team")
        .order_by(
            "nombre_comercial",
            "nombre_fiscal",
            "id",
        )
    )

    selected = {}

    for proveedor in qs:
        cif = (
            proveedor.cif or ""
        ).strip().upper()

        nombre = (
            proveedor.nombre_comercial
            or proveedor.nombre_fiscal
            or ""
        ).strip()

        key = (
            f"CIF:{cif}"
            if cif
            else f"NOMBRE:{nombre.lower()}"
        )

        current = selected.get(key)

        if current is None:
            selected[key] = proveedor
            continue

        if (
            preferred_team_id
            and proveedor.team_id
            == preferred_team_id
        ):
            selected[key] = proveedor

    result = []

    for proveedor in sorted(
        selected.values(),
        key=lambda p: (
            (
                p.nombre_comercial
                or p.nombre_fiscal
                or ""
            ).lower(),
            p.pk,
        ),
    ):
        nombre = (
            proveedor.nombre_comercial
            or proveedor.nombre_fiscal
            or f"Proveedor {proveedor.pk}"
        )

        result.append({
            "id": proveedor.pk,
            "team_id": proveedor.team_id,
            "label": nombre,
            "nombre": nombre,
            "nif": proveedor.cif or "",
            "email": proveedor.email or "",
            "telefono": proveedor.telefono or "",
        })

    return result


def resolve_proveedor(team_scope, proveedor_id):
    from apps.gestion.models import Proveedor

    try:
        proveedor_id = int(proveedor_id)
    except (TypeError, ValueError):
        return None

    proveedor = (
        Proveedor.objects
        .select_related("team")
        .filter(
            pk=proveedor_id,
            team__in=team_scope,
            activo=True,
        )
        .first()
    )

    if not proveedor:
        return None

    nombre = (
        proveedor.nombre_comercial
        or proveedor.nombre_fiscal
        or f"Proveedor {proveedor.pk}"
    )

    return {
        "id": proveedor.pk,
        "team_id": proveedor.team_id,
        "nombre": nombre,
        "nif": proveedor.cif or "",
        "email": proveedor.email or "",
        "telefono": proveedor.telefono or "",
    }


# COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1

def get_proveedores_options_for_team(
    team_id,
):
    from apps.gestion.models import (
        Proveedor,
    )

    qs = (
        Proveedor.objects
        .filter(
            team_id=team_id,
            activo=True,
        )
        .order_by(
            "nombre_comercial",
            "nombre_fiscal",
            "id",
        )
    )

    result = []

    for proveedor in qs:
        nombre = (
            proveedor.nombre_comercial
            or proveedor.nombre_fiscal
            or f"Proveedor {proveedor.pk}"
        )

        label = nombre

        if proveedor.cif:
            label = (
                f"{nombre} · "
                f"{proveedor.cif}"
            )

        result.append({
            "id": proveedor.pk,
            "team_id": (
                proveedor.team_id
            ),
            "label": label,
            "nombre": nombre,
            "nif": (
                proveedor.cif or ""
            ),
            "email": (
                proveedor.email or ""
            ),
            "telefono": (
                proveedor.telefono
                or ""
            ),
        })

    return result


def get_proveedores_matching_data(
    team_id,
):
    from apps.gestion.models import (
        Proveedor,
    )

    qs = (
        Proveedor.objects
        .filter(
            team_id=team_id,
            activo=True,
        )
        .order_by("id")
    )

    return [
        {
            "id": proveedor.pk,
            "team_id": (
                proveedor.team_id
            ),
            "nombre_comercial": (
                proveedor.nombre_comercial
                or ""
            ),
            "nombre_fiscal": (
                proveedor.nombre_fiscal
                or ""
            ),
            "cif": (
                proveedor.cif or ""
            ),
        }
        for proveedor in qs
    ]


def resolve_proveedor_for_team(
    team_id,
    proveedor_id,
):
    from apps.gestion.models import (
        Proveedor,
    )

    try:
        proveedor_id = int(
            proveedor_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    proveedor = (
        Proveedor.objects
        .filter(
            pk=proveedor_id,
            team_id=team_id,
            activo=True,
        )
        .first()
    )

    if not proveedor:
        return None

    nombre = (
        proveedor.nombre_comercial
        or proveedor.nombre_fiscal
        or f"Proveedor {proveedor.pk}"
    )

    return {
        "id": proveedor.pk,
        "team_id": (
            proveedor.team_id
        ),
        "nombre": nombre,
        "nif": (
            proveedor.cif or ""
        ),
        "email": (
            proveedor.email or ""
        ),
        "telefono": (
            proveedor.telefono or ""
        ),
    }
