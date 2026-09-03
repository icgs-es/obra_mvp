"""
Política central de autorización para INTASA Cloud.

La autorización resulta de la intersección entre:

1. ámbito funcional de la raíz documental;
2. capacidad Django de lectura o gestión.

Los usuarios staff no reciben bypass documental.
El bypass completo se reserva al superusuario.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.core.exceptions import (
    PermissionDenied,
)

from .models import ReglaAccesoRaizCloud


READ_FOLDER_PERMISSION = (
    "archivos.view_carpeta"
)

READ_FILE_PERMISSION = (
    "archivos.view_archivo"
)


class CloudPathPolicyError(
    ValueError
):
    """Ruta Cloud no válida."""


def normalize_cloud_policy_path(
    value: Any,
) -> str:
    """
    Normaliza una ruta lógica relativa.

    No acepta segmentos ascendentes ni rutas
    absolutas externas al almacenamiento.
    """

    raw = str(
        value
        or ""
    ).replace(
        "\\",
        "/",
    ).strip()

    raw = raw.strip("/")

    if not raw:
        return ""

    parts = []

    for part in raw.split("/"):
        token = part.strip()

        if not token:
            continue

        if token in {
            ".",
            "..",
        }:
            raise CloudPathPolicyError(
                "La ruta documental no es válida."
            )

        parts.append(
            token
        )

    return "/".join(
        parts
    )


def cloud_root_name(
    path: Any,
) -> str:
    normalized = (
        normalize_cloud_policy_path(
            path
        )
    )

    if not normalized:
        return ""

    return normalized.split(
        "/",
        1,
    )[0]


def _is_authenticated(
    user,
) -> bool:
    return bool(
        user is not None
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    )


def _is_superuser(
    user,
) -> bool:
    return bool(
        _is_authenticated(user)
        and getattr(
            user,
            "is_superuser",
            False,
        )
    )


def _user_group_ids(
    user,
) -> set[int]:
    if not _is_authenticated(
        user
    ):
        return set()

    return set(
        user.groups.values_list(
            "id",
            flat=True,
        )
    )


def active_cloud_root_rules():
    return (
        ReglaAccesoRaizCloud.objects
        .filter(
            activa=True
        )
        .prefetch_related(
            "grupos",
        )
        .order_by(
            "nombre_raiz",
        )
    )


def cloud_root_scope_allowed(
    user,
    root_name: Any,
) -> bool:
    """
    Comprueba únicamente el ámbito funcional.

    No evalúa todavía el permiso de lectura,
    creación o modificación.
    """

    if _is_superuser(
        user
    ):
        return True

    if not _is_authenticated(
        user
    ):
        return False

    normalized_root = (
        cloud_root_name(
            root_name
        )
    )

    if not normalized_root:
        return True

    rule = (
        ReglaAccesoRaizCloud.objects
        .filter(
            activa=True,
            nombre_raiz__iexact=(
                normalized_root
            ),
        )
        .prefetch_related(
            "grupos",
        )
        .first()
    )

    if rule is None:
        return False

    if rule.visible_para_todos:
        return True

    user_group_ids = (
        _user_group_ids(
            user
        )
    )

    if not user_group_ids:
        return False

    return rule.grupos.filter(
        id__in=user_group_ids
    ).exists()


def cloud_path_allowed(
    user,
    path: Any,
    *,
    permission: str,
) -> bool:
    """
    Comprueba ámbito funcional y capacidad.

    El atributo is_staff no concede acceso.
    """

    if _is_superuser(
        user
    ):
        return True

    if not _is_authenticated(
        user
    ):
        return False

    if not user.has_perm(
        permission
    ):
        return False

    root_name = cloud_root_name(
        path
    )

    return cloud_root_scope_allowed(
        user,
        root_name,
    )


def cloud_folder_read_allowed(
    user,
    path: Any,
) -> bool:
    return cloud_path_allowed(
        user,
        path,
        permission=(
            READ_FOLDER_PERMISSION
        ),
    )


def cloud_file_read_allowed(
    user,
    path: Any,
) -> bool:
    return cloud_path_allowed(
        user,
        path,
        permission=(
            READ_FILE_PERMISSION
        ),
    )


def cloud_write_allowed(
    user,
    path: Any,
    *,
    permission: str,
) -> bool:
    return cloud_path_allowed(
        user,
        path,
        permission=permission,
    )


def require_cloud_path(
    user,
    path: Any,
    *,
    permission: str,
) -> str:
    normalized = (
        normalize_cloud_policy_path(
            path
        )
    )

    if not cloud_path_allowed(
        user,
        normalized,
        permission=permission,
    ):
        raise PermissionDenied(
            "No tienes acceso a esta "
            "ubicación documental."
        )

    return normalized


def allowed_cloud_root_names(
    user,
    *,
    permission: str,
) -> set[str] | None:
    """
    Devuelve las raíces autorizadas.

    None significa acceso ilimitado de
    superusuario.
    """

    if _is_superuser(
        user
    ):
        return None

    if not _is_authenticated(
        user
    ):
        return set()

    if not user.has_perm(
        permission
    ):
        return set()

    user_group_ids = (
        _user_group_ids(
            user
        )
    )

    result = set()

    for rule in (
        active_cloud_root_rules()
    ):
        if rule.visible_para_todos:
            result.add(
                rule.nombre_raiz
            )

            continue

        rule_group_ids = {
            group.pk
            for group
            in rule.grupos.all()
        }

        if (
            user_group_ids
            & rule_group_ids
        ):
            result.add(
                rule.nombre_raiz
            )

    return result


def filter_cloud_root_items(
    user,
    items: Iterable[dict],
    *,
    permission: str = (
        READ_FOLDER_PERMISSION
    ),
) -> list[dict]:
    allowed = (
        allowed_cloud_root_names(
            user,
            permission=permission,
        )
    )

    if allowed is None:
        return list(items)

    allowed_casefold = {
        name.casefold()
        for name in allowed
    }

    return [
        item
        for item in items
        if str(
            item.get("name")
            or ""
        ).casefold()
        in allowed_casefold
    ]
