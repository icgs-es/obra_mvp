from __future__ import annotations
import logging
from .cloud_activity import registrar_operacion_cloud, snapshot_cloud_references

from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponseForbidden,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import (
    url_has_allowed_host_and_scheme,
)
from django.views.decorators.http import (
    require_http_methods,
)

from .cloud_gateway import (
    CloudGatewayError,
    NextcloudCloudGateway,
)
from .models import Archivo

from .cloud_rbac import (
    allowed_cloud_root_names,
    cloud_path_allowed,
    cloud_root_scope_allowed,
)

logger = logging.getLogger(__name__)


def _can_manage(
    user,
    path,
    *,
    permission,
) -> bool:
    """
    ARCHIVOS_CLOUD_ACTIONS_RBAC_V1A

    La autorización documental combina:

      permiso Django + ámbito de raíz.

    El estado staff no concede bypass.
    El bypass completo se reserva a superusuario.
    """
    return cloud_path_allowed(
        user,
        path,
        permission=permission,
    )


def _business_roots(
    gateway: NextcloudCloudGateway,
) -> set[str]:
    configured = (
        gateway.config.get(
            "business_root_items"
        )
        or []
    )

    if not isinstance(configured, list):
        raise CloudGatewayError(
            "La configuración de raíces "
            "empresariales no es válida."
        )

    return {
        str(name).strip()
        for name in configured
        if str(name).strip()
    }


def _is_protected_root(
    gateway: NextcloudCloudGateway,
    storage_key: str,
) -> bool:
    return (
        "/" not in storage_key
        and storage_key
        in _business_roots(gateway)
    )


def _parent_path(storage_key: str) -> str:
    parent = str(
        PurePosixPath(storage_key).parent
    )

    return "" if parent == "." else parent


def _explorer_url(path: str = "") -> str:
    url = reverse(
        "archivos:explorador_raiz"
    )

    normalized = str(path or "").strip("/")

    if normalized:
        from urllib.parse import urlencode

        url += "?" + urlencode(
            {
                "path": normalized,
            }
        )

    return url


def _safe_cancel_url(
    request,
    fallback: str,
) -> str:
    candidate = str(
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    ).strip()

    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={
            request.get_host(),
        },
        require_https=request.is_secure(),
    ):
        return candidate

    return fallback


def _request_path(
    request,
    gateway: NextcloudCloudGateway,
) -> str:
    value = (
        request.POST.get("path")
        if request.method == "POST"
        else request.GET.get("path")
    )

    return gateway.normalize_path(
        value or "",
        allow_empty=False,
    )


def _update_reference_paths(
    source: str,
    destination: str,
    *,
    exact_name: str | None = None,
    exact_etag: str = "",
) -> int:
    updated = 0

    with transaction.atomic():
        references = list(
            Archivo.objects
            .select_for_update()
            .filter(
                storage_provider="nextcloud",
            )
            .filter(
                Q(storage_key=source)
                | Q(
                    storage_key__startswith=(
                        source + "/"
                    )
                )
            )
            .order_by("pk")
        )

        for reference in references:
            old_key = reference.storage_key

            suffix = old_key[
                len(source):
            ]

            reference.storage_key = (
                destination + suffix
            )

            update_fields = [
                "storage_key",
            ]

            if (
                old_key == source
                and exact_name
            ):
                reference.nombre_original = (
                    exact_name
                )
                reference.nombre_logico = (
                    exact_name
                )

                update_fields.extend(
                    [
                        "nombre_original",
                        "nombre_logico",
                    ]
                )

                if exact_etag:
                    reference.storage_version = (
                        exact_etag
                    )
                    update_fields.append(
                        "storage_version"
                    )

            reference.save(
                update_fields=update_fields
            )

            updated += 1

    return updated


def _delete_reference_paths(
    source: str,
) -> int:
    with transaction.atomic():
        deleted, detail = (
            Archivo.objects
            .filter(
                storage_provider="nextcloud",
            )
            .filter(
                Q(storage_key=source)
                | Q(
                    storage_key__startswith=(
                        source + "/"
                    )
                )
            )
            .delete()
        )

    return int(
        detail.get(
            Archivo._meta.label,
            0,
        )
    )


def _validate_destination_parent(
    gateway: NextcloudCloudGateway,
    destination_parent: str,
) -> str:
    parent = gateway.normalize_path(
        destination_parent,
        allow_empty=False,
    )

    root_name = parent.split("/", 1)[0]

    if root_name not in _business_roots(
        gateway
    ):
        raise CloudGatewayError(
            "El destino debe estar dentro de "
            "una carpeta empresarial."
        )

    item = gateway.get_item(parent)

    if not item["is_folder"]:
        raise CloudGatewayError(
            "El destino no es una carpeta."
        )

    return parent


def _destination_browser(
    gateway: NextcloudCloudGateway,
    source: str,
    item: dict,
    browse_path: str,
    *,
    user,
) -> dict:
    """
    Navegador progresivo de destinos.

    Solo consulta el nivel que el usuario está viendo.
    No recorre previamente todo el árbol documental.
    """
    browse = gateway.normalize_path(
        browse_path,
        allow_empty=True,
    )

    business_roots = sorted(
        _business_roots(gateway),
        key=str.casefold,
    )

    source_is_folder = bool(
        item.get("is_folder")
    )

    destination_permission = (
        "archivos.add_carpeta"
        if source_is_folder
        else "archivos.add_archivo"
    )

    allowed_roots = (
        allowed_cloud_root_names(
            user,
            permission=destination_permission,
        )
    )

    if allowed_roots is not None:

        allowed_casefold = {
            value.casefold()
            for value in allowed_roots
        }

        business_roots = [
            value
            for value in business_roots
            if value.casefold()
            in allowed_casefold
        ]

    source_prefix = source + "/"
    source_parent = _parent_path(source)

    def is_blocked(path: str) -> bool:
        return bool(
            path == source
            or (
                source_is_folder
                and path.startswith(
                    source_prefix
                )
            )
        )

    if browse:
        root_name = browse.split("/", 1)[0]

        if root_name not in business_roots:
            raise CloudGatewayError(
                "La carpeta no pertenece a "
                "tu ámbito documental autorizado."
            )

        if not cloud_path_allowed(
            user,
            browse,
            permission=destination_permission,
        ):
            raise CloudGatewayError(
                "No tienes permisos para usar "
                "esta ubicación como destino."
            )

        if is_blocked(browse):
            raise CloudGatewayError(
                "No se puede seleccionar la carpeta "
                "origen ni una de sus subcarpetas."
            )

        current_item = gateway.get_item(
            browse
        )

        if not current_item["is_folder"]:
            raise CloudGatewayError(
                "El destino no es una carpeta."
            )

        children = [
            child
            for child in gateway.list_directory(
                browse
            )
            if child["is_folder"]
            and not is_blocked(
                str(child["storage_key"])
            )
        ]

        current_permissions = str(
            current_item.get("permissions")
            or ""
        )

        can_move_here = bool(
            "C" in current_permissions
            and browse != source_parent
        )

    else:
        children = []

        for root_name in business_roots:
            if is_blocked(root_name):
                continue

            try:
                root_item = gateway.get_item(
                    root_name
                )
            except FileNotFoundError:
                continue

            if root_item["is_folder"]:
                children.append(root_item)

        can_move_here = False

    children.sort(
        key=lambda child: (
            str(child["name"]).casefold()
        )
    )

    parts = [
        part
        for part in browse.split("/")
        if part
    ]

    breadcrumbs = [
        {
            "name": "Carpetas principales",
            "path": "",
        }
    ]

    accumulated = []

    for part in parts:
        accumulated.append(part)

        breadcrumbs.append(
            {
                "name": part,
                "path": "/".join(
                    accumulated
                ),
            }
        )

    browse_parent = None

    if parts:
        browse_parent = "/".join(
            parts[:-1]
        )

    return {
        "browse_path": browse,
        "browse_parent": browse_parent,
        "browse_folders": children,
        "destination_breadcrumbs": breadcrumbs,
        "can_move_here": can_move_here,
    }


@login_required
@require_http_methods(["GET", "POST"])
def cloud_item_rename(request):
    gateway = NextcloudCloudGateway()

    try:
        source = _request_path(
            request,
            gateway,
        )

        if not cloud_root_scope_allowed(
            request.user,
            source,
        ):
            return HttpResponseForbidden(
                "No tienes acceso a esta "
                "ubicación documental."
            )

        item = gateway.get_item(
            source
        )

        permission = (
            "archivos.change_carpeta"
            if item.get("is_folder")
            else "archivos.change_archivo"
        )

        if not _can_manage(
            request.user,
            source,
            permission=permission,
        ):
            return HttpResponseForbidden(
                "No tienes permisos para renombrar."
            )

        if _is_protected_root(
            gateway,
            source,
        ):
            raise CloudGatewayError(
                "Las carpetas empresariales raíz "
                "no se pueden renombrar."
            )

        parent = _parent_path(
            source
        )

        cancel_url = _safe_cancel_url(
            request,
            _explorer_url(parent),
        )

        if request.method == "POST":
            try:
                snapshot = (
                    snapshot_cloud_references(
                        source
                    )
                )
            except Exception:
                logger.exception(
                    "No se pudieron capturar "
                    "las referencias antes "
                    "de renombrar.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                    },
                )

                snapshot = None

            new_name = (
                gateway.normalize_name(
                    request.POST.get(
                        "name",
                        "",
                    )
                )
            )

            destination = "/".join(
                value
                for value in (
                    parent,
                    new_name,
                )
                if value
            )

            moved = gateway.move_path(
                source,
                destination,
            )

            updated = (
                _update_reference_paths(
                    source,
                    destination,
                    exact_name=(
                        new_name
                        if not item[
                            "is_folder"
                        ]
                        else None
                    ),
                    exact_etag=str(
                        moved.get(
                            "etag"
                        )
                        or ""
                    ),
                )
            )

            try:
                registrar_operacion_cloud(
                    request=request,
                    accion="renombrar",
                    item=item,
                    source=source,
                    destination=destination,
                    snapshot=snapshot,
                    references_affected=(
                        updated
                    ),
                    url=_explorer_url(
                        parent
                    ),
                )

            except Exception:
                logger.exception(
                    "El elemento remoto se "
                    "renombró, pero no pudo "
                    "registrarse su actividad.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                        "destination": (
                            destination
                        ),
                    },
                )

                messages.warning(
                    request,
                    (
                        "El elemento se renombró, "
                        "pero su actividad no pudo "
                        "incorporarse al panel."
                    ),
                )

            messages.success(
                request,
                (
                    "Elemento renombrado. "
                    "Referencias actualizadas: "
                    f"{updated}."
                ),
            )

            return redirect(
                _explorer_url(parent)
            )

        return render(
            request,
            "archivos/cloud_action_form.html",
            {
                "action": "rename",
                "title": "Renombrar",
                "item": item,
                "current_path": source,
                "current_parent": parent,
                "cancel_url": cancel_url,
                "business_roots": sorted(
                    _business_roots(
                        gateway
                    ),
                    key=str.casefold,
                ),
            },
        )

    except FileNotFoundError:
        raise Http404(
            "El elemento no existe."
        )

    except CloudGatewayError as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            _safe_cancel_url(
                request,
                _explorer_url(""),
            )
        )


@login_required
@require_http_methods(["GET", "POST"])
def cloud_item_move(request):
    gateway = NextcloudCloudGateway()

    try:
        source = _request_path(
            request,
            gateway,
        )

        if not cloud_root_scope_allowed(
            request.user,
            source,
        ):
            return HttpResponseForbidden(
                "No tienes acceso a esta "
                "ubicación documental."
            )

        item = gateway.get_item(
            source
        )

        source_permission = (
            "archivos.change_carpeta"
            if item.get("is_folder")
            else "archivos.change_archivo"
        )

        if not _can_manage(
            request.user,
            source,
            permission=source_permission,
        ):
            return HttpResponseForbidden(
                "No tienes permisos para mover."
            )

        if _is_protected_root(
            gateway,
            source,
        ):
            raise CloudGatewayError(
                "Las carpetas empresariales raíz "
                "no se pueden mover."
            )

        source_parent = (
            _parent_path(source)
        )

        cancel_url = _safe_cancel_url(
            request,
            _explorer_url(
                source_parent
            ),
        )

        if request.method == "POST":
            try:
                snapshot = (
                    snapshot_cloud_references(
                        source
                    )
                )
            except Exception:
                logger.exception(
                    "No se pudieron capturar "
                    "las referencias antes "
                    "de mover.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                    },
                )

                snapshot = None

            destination_parent = (
                _validate_destination_parent(
                    gateway,
                    request.POST.get(
                        "destination_path",
                        "",
                    ),
                )
            )

            destination_permission = (
                "archivos.add_carpeta"
                if item.get("is_folder")
                else "archivos.add_archivo"
            )

            if not cloud_path_allowed(
                request.user,
                destination_parent,
                permission=destination_permission,
            ):
                return HttpResponseForbidden(
                    "No tienes permisos para mover "
                    "el elemento a ese destino."
                )

            destination = (
                destination_parent
                + "/"
                + PurePosixPath(
                    source
                ).name
            )

            moved = gateway.move_path(
                source,
                destination,
            )

            updated = (
                _update_reference_paths(
                    source,
                    destination,
                    exact_name=(
                        PurePosixPath(
                            destination
                        ).name
                        if not item[
                            "is_folder"
                        ]
                        else None
                    ),
                    exact_etag=str(
                        moved.get(
                            "etag"
                        )
                        or ""
                    ),
                )
            )

            try:
                registrar_operacion_cloud(
                    request=request,
                    accion="mover",
                    item=item,
                    source=source,
                    destination=destination,
                    snapshot=snapshot,
                    references_affected=(
                        updated
                    ),
                    url=_explorer_url(
                        destination_parent
                    ),
                )

            except Exception:
                logger.exception(
                    "El elemento remoto se movió, "
                    "pero no pudo registrarse "
                    "su actividad.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                        "destination": (
                            destination
                        ),
                    },
                )

                messages.warning(
                    request,
                    (
                        "El elemento se movió, "
                        "pero su actividad no pudo "
                        "incorporarse al panel."
                    ),
                )

            messages.success(
                request,
                (
                    "Elemento movido. "
                    "Referencias actualizadas: "
                    f"{updated}."
                ),
            )

            return redirect(
                _explorer_url(
                    destination_parent
                )
            )

        browse_path = (
            gateway.normalize_path(
                request.GET.get(
                    "browse",
                    "",
                ),
                allow_empty=True,
            )
        )

        browser = (
            _destination_browser(
                gateway,
                source,
                item,
                browse_path,
                user=request.user,
            )
        )

        return render(
            request,
            "archivos/cloud_action_form.html",
            {
                "action": "move",
                "title": "Mover",
                "item": item,
                "current_path": source,
                "current_parent": (
                    source_parent
                ),
                "cancel_url": cancel_url,
                **browser,
            },
        )

    except FileNotFoundError:
        raise Http404(
            "El elemento no existe."
        )

    except CloudGatewayError as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            _safe_cancel_url(
                request,
                _explorer_url(""),
            )
        )


@login_required
@require_http_methods(["GET", "POST"])
def cloud_item_delete(request):
    gateway = NextcloudCloudGateway()

    try:
        source = _request_path(
            request,
            gateway,
        )

        if not cloud_root_scope_allowed(
            request.user,
            source,
        ):
            return HttpResponseForbidden(
                "No tienes acceso a esta "
                "ubicación documental."
            )

        item = gateway.get_item(
            source
        )

        permission = (
            "archivos.delete_carpeta"
            if item.get("is_folder")
            else "archivos.delete_archivo"
        )

        if not _can_manage(
            request.user,
            source,
            permission=permission,
        ):
            return HttpResponseForbidden(
                "No tienes permisos para eliminar."
            )

        if _is_protected_root(
            gateway,
            source,
        ):
            raise CloudGatewayError(
                "Las carpetas empresariales raíz "
                "no se pueden eliminar."
            )

        parent = _parent_path(
            source
        )

        cancel_url = _safe_cancel_url(
            request,
            _explorer_url(parent),
        )

        if request.method == "POST":
            try:
                snapshot = (
                    snapshot_cloud_references(
                        source
                    )
                )
            except Exception:
                logger.exception(
                    "No se pudieron capturar "
                    "las referencias antes "
                    "de eliminar.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                    },
                )

                snapshot = None

            gateway.delete_path(
                source
            )

            deleted = (
                _delete_reference_paths(
                    source
                )
            )

            try:
                registrar_operacion_cloud(
                    request=request,
                    accion="eliminar",
                    item=item,
                    source=source,
                    snapshot=snapshot,
                    references_affected=(
                        deleted
                    ),
                    url=_explorer_url(
                        parent
                    ),
                )

            except Exception:
                logger.exception(
                    "El elemento remoto se "
                    "eliminó, pero no pudo "
                    "registrarse su actividad.",
                    extra={
                        "actor_id": (
                            request.user.pk
                        ),
                        "source": source,
                    },
                )

                messages.warning(
                    request,
                    (
                        "El elemento se eliminó, "
                        "pero su actividad no pudo "
                        "incorporarse al panel."
                    ),
                )

            messages.success(
                request,
                (
                    "Elemento eliminado de "
                    "INTASA Documents. "
                    "Referencias retiradas: "
                    f"{deleted}."
                ),
            )

            return redirect(
                _explorer_url(parent)
            )

        return render(
            request,
            "archivos/cloud_delete_confirm.html",
            {
                "item": item,
                "current_path": source,
                "cancel_url": cancel_url,
            },
        )

    except FileNotFoundError:
        raise Http404(
            "El elemento no existe."
        )

    except CloudGatewayError as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            _safe_cancel_url(
                request,
                _explorer_url(""),
            )
        )
