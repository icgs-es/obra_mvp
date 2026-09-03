from __future__ import annotations
from .cloud_activity import registrar_operacion_cloud, snapshot_cloud_references

import logging
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseForbidden,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import (
    url_has_allowed_host_and_scheme,
)
from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from .cloud_gateway import (
    CloudGatewayError,
    NextcloudCloudGateway,
)
from .models import Archivo, Carpeta
from .activity import (
    registrar_subida_documental,
)
from .cloud_references import (
    CloudReferenceError,
    upsert_cloud_uploaded_reference,
)
from .team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)


logger = logging.getLogger(__name__)

CLOUD_INDEX_SLUG = "intasa-cloud-system"


def _human_size(size: int) -> str:
    value = float(size or 0)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"

            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{int(size or 0)} B"


def _breadcrumbs(path: str) -> list[dict]:
    crumbs = [
        {
            "name": "Archivos",
            "path": "",
        }
    ]

    current = []

    for segment in path.split("/"):
        if not segment:
            continue

        current.append(segment)

        crumbs.append(
            {
                "name": segment,
                "path": "/".join(current),
            }
        )

    return crumbs


def _cloud_index_folder() -> Carpeta:
    try:
        return Carpeta.objects.get(
            slug=CLOUD_INDEX_SLUG
        )
    except Carpeta.DoesNotExist as exc:
        raise CloudGatewayError(
            "No está configurado el índice documental."
        ) from exc


@login_required
@require_GET
def cloud_explorer(request):
    from datetime import (
        timezone as datetime_timezone,
    )
    from email.utils import (
        parsedate_to_datetime,
    )
    from urllib.parse import urlencode

    from django.urls import reverse
    from django.utils import (
        timezone as django_timezone,
    )

    gateway = NextcloudCloudGateway()

    sort_field = str(
        request.GET.get("sort")
        or "name"
    ).strip().lower()

    if sort_field not in {
        "name",
        "date",
    }:
        sort_field = "name"

    sort_direction = str(
        request.GET.get("dir")
        or "asc"
    ).strip().lower()

    if sort_direction not in {
        "asc",
        "desc",
    }:
        sort_direction = (
            "desc"
            if sort_field == "date"
            else "asc"
        )

    try:
        current_path = gateway.normalize_path(
            request.GET.get("path", ""),
            allow_empty=True,
        )

        items = gateway.list_directory(
            current_path
        )

        if not current_path:
            configured_hidden = (
                gateway.config.get(
                    "hidden_root_items"
                )
                or []
            )

            if not isinstance(
                configured_hidden,
                list,
            ):
                raise CloudGatewayError(
                    "La configuración de elementos "
                    "ocultos no es válida."
                )

            hidden_root_names = {
                str(name).strip()
                for name in configured_hidden
                if str(name).strip()
            }

            items = [
                item
                for item in items
                if item["name"]
                not in hidden_root_names
            ]

        error = ""

    except FileNotFoundError:
        raise Http404(
            "La carpeta documental no existe."
        )

    except CloudGatewayError:
        current_path = ""
        items = []
        error = (
            "No se pudo cargar el "
            "almacenamiento documental."
        )

    for item in items:
        item["size_label"] = _human_size(
            item.get("size") or 0
        )

        raw_modified = str(
            item.get("modified")
            or ""
        ).strip()

        modified_datetime = None

        if raw_modified:
            try:
                modified_datetime = (
                    parsedate_to_datetime(
                        raw_modified
                    )
                )

                if (
                    modified_datetime.tzinfo
                    is None
                ):
                    modified_datetime = (
                        modified_datetime.replace(
                            tzinfo=(
                                datetime_timezone.utc
                            )
                        )
                    )

                modified_datetime = (
                    django_timezone.localtime(
                        modified_datetime
                    )
                )

            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                modified_datetime = None

        item["modified_datetime"] = (
            modified_datetime
        )

        item["modified_sort"] = (
            modified_datetime.timestamp()
            if modified_datetime
            else None
        )

        item["modified_label"] = (
            modified_datetime.strftime(
                "%d/%m/%Y %H:%M"
            )
            if modified_datetime
            else "—"
        )

    reverse_sort = (
        sort_direction == "desc"
    )

    folders = [
        item
        for item in items
        if item["is_folder"]
    ]

    files = [
        item
        for item in items
        if not item["is_folder"]
    ]

    def sort_group(group):
        if sort_field == "date":
            known_date = [
                item
                for item in group
                if item["modified_sort"]
                is not None
            ]

            unknown_date = [
                item
                for item in group
                if item["modified_sort"]
                is None
            ]

            known_date.sort(
                key=lambda item: (
                    item["modified_sort"]
                ),
                reverse=reverse_sort,
            )

            unknown_date.sort(
                key=lambda item: (
                    item["name"].casefold()
                )
            )

            return (
                known_date
                + unknown_date
            )

        return sorted(
            group,
            key=lambda item: (
                item["name"].casefold()
            ),
            reverse=reverse_sort,
        )

    items = (
        sort_group(folders)
        + sort_group(files)
    )

    path_parts = [
        part
        for part in current_path.split("/")
        if part
    ]

    parent_path = (
        "/".join(path_parts[:-1])
        if path_parts
        else None
    )

    explorer_base_url = reverse(
        "archivos:explorador_raiz"
    )

    def explorer_url(
        path_value="",
        *,
        field=None,
        direction=None,
    ):
        params = {}

        if path_value:
            params["path"] = path_value

        params["sort"] = (
            field
            or sort_field
        )

        params["dir"] = (
            direction
            or sort_direction
        )

        return (
            explorer_base_url
            + "?"
            + urlencode(params)
        )

    for item in items:
        if item["is_folder"]:
            item["browse_url"] = (
                explorer_url(
                    item["storage_key"]
                )
            )

    breadcrumbs = [
        {
            "name": "Archivos",
            "path": "",
            "url": explorer_url(""),
        }
    ]

    accumulated_path = []

    for part in path_parts:
        accumulated_path.append(part)

        crumb_path = "/".join(
            accumulated_path
        )

        breadcrumbs.append(
            {
                "name": part,
                "path": crumb_path,
                "url": explorer_url(
                    crumb_path
                ),
            }
        )

    name_next_direction = (
        "desc"
        if (
            sort_field == "name"
            and sort_direction == "asc"
        )
        else "asc"
    )

    date_next_direction = (
        "asc"
        if (
            sort_field == "date"
            and sort_direction == "desc"
        )
        else "desc"
    )

    current_url = explorer_url(
        current_path
    )


    # ARCHIVOS_MANAGEMENT_COMPLETE_CONTEXT_V1
    can_manage_actions = (
        request.user.is_superuser
        or all(
            request.user.has_perm(
                permission
            )
            for permission in (
                "archivos.change_archivo",
                "archivos.change_carpeta",
                "archivos.delete_archivo",
                "archivos.delete_carpeta",
            )
        )
    )

    context = {
        "can_manage_actions": can_manage_actions,
        "items": items,
        "current_path": current_path,
        "current_name": (
            path_parts[-1]
            if path_parts
            else "Archivos"
        ),
        "parent_path": parent_path,
        "parent_url": (
            explorer_url(parent_path)
            if parent_path is not None
            else ""
        ),
        "breadcrumbs": breadcrumbs,
        "current_url": current_url,
        "sort_field": sort_field,
        "sort_direction": sort_direction,
        "sort_name_url": explorer_url(
            current_path,
            field="name",
            direction=name_next_direction,
        ),
        "sort_date_url": explorer_url(
            current_path,
            field="date",
            direction=date_next_direction,
        ),
        "error": error,
    }

    return render(
        request,
        "archivos/cloud_explorer.html",
        context,
        status=503 if error else 200,
    )




@login_required
@require_GET
def cloud_file_open(request):
    gateway = NextcloudCloudGateway()

    try:
        storage_key = gateway.normalize_path(
            request.GET.get("path", ""),
            allow_empty=False,
        )

        item = gateway.get_item(
            storage_key
        )

    except FileNotFoundError:
        raise Http404(
            "El archivo documental no existe."
        )

    except CloudGatewayError as exc:
        return HttpResponse(
            str(exc),
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    if item["is_folder"]:
        raise Http404(
            "La referencia corresponde a una carpeta."
        )

    requested_file_id = str(
        request.GET.get("file_id") or ""
    ).strip()

    remote_file_id = str(
        item.get("file_id") or ""
    ).strip()

    if (
        requested_file_id
        and requested_file_id != remote_file_id
    ):
        raise Http404(
            "El identificador documental no coincide."
        )

    if not remote_file_id:
        return HttpResponse(
            "El documento no tiene identificador remoto.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    filename = PurePosixPath(
        storage_key
    ).name

    content_type = (
        item.get("content_type")
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    cloud_folder = _cloud_index_folder()

    with transaction.atomic():
        matches = (
            Archivo.objects
            .select_for_update()
            .filter(
                storage_provider="nextcloud",
                storage_object_id=remote_file_id,
            )
            .order_by("pk")
        )

        if matches.count() > 1:
            return HttpResponse(
                "Existen referencias documentales duplicadas.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )

        archivo = matches.first()

        if archivo is None:
            archivo = Archivo.objects.create(
                carpeta=cloud_folder,
                fichero="",
                nombre_original=filename,
                nombre_logico=filename,
                descripcion="",
                subido_por=request.user,
                tamano_bytes=int(
                    item.get("size") or 0
                ),
                version=1,
                storage_provider="nextcloud",
                storage_key=storage_key,
                storage_object_id=remote_file_id,
                storage_version=str(
                    item.get("etag") or ""
                ),
                mime_type=content_type,
            )
        else:
            archivo.carpeta = cloud_folder
            archivo.fichero = ""
            archivo.nombre_original = filename
            archivo.nombre_logico = filename
            archivo.tamano_bytes = int(
                item.get("size") or 0
            )
            archivo.storage_key = storage_key
            archivo.storage_version = str(
                item.get("etag") or ""
            )
            archivo.mime_type = content_type

            if archivo.subido_por_id is None:
                archivo.subido_por = request.user

            archivo.save(
                update_fields=[
                    "carpeta",
                    "fichero",
                    "nombre_original",
                    "nombre_logico",
                    "tamano_bytes",
                    "storage_key",
                    "storage_version",
                    "mime_type",
                    "subido_por",
                ]
            )

    next_url = str(
        request.GET.get("next") or ""
    ).strip()

    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        parent = str(
            PurePosixPath(storage_key).parent
        )

        if parent == ".":
            parent = ""

        next_url = reverse(
            "archivos:explorador_raiz"
        )

        if parent:
            next_url += "?" + urlencode(
                {
                    "path": parent,
                }
            )

    detail_url = reverse(
        "archivos:archivo_detalle",
        args=[archivo.pk],
    )

    return redirect(
        detail_url
        + "?"
        + urlencode(
            {
                "next": next_url,
            }
        )
    )


# CLOUD_MANAGEMENT_PERMISSION_RBAC_V1
CLOUD_CREATE_FOLDER_PERMISSION = (
    "archivos.add_carpeta"
)

CLOUD_UPLOAD_FILE_PERMISSION = (
    "archivos.add_archivo"
)

CLOUD_MANAGEMENT_PERMISSIONS = (
    CLOUD_CREATE_FOLDER_PERMISSION,
    CLOUD_UPLOAD_FILE_PERMISSION,
    "archivos.upload_folder",
)


def _can_manage_cloud(
    user,
    permission=None,
) -> bool:
    """
    Autoriza mediante los permisos configurables
    del usuario.

    El bypass completo se reserva al superusuario.
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if permission:
        return user.has_perm(
            permission
        )

    return any(
        user.has_perm(item)
        for item in (
            CLOUD_MANAGEMENT_PERMISSIONS
        )
    )


def _cloud_explorer_url(path: str = "") -> str:
    normalized = str(path or "").strip("/")

    url = reverse(
        "archivos:explorador_raiz"
    )

    if normalized:
        url += "?" + urlencode(
            {
                "path": normalized,
            }
        )

    return url


@login_required
@require_POST
def cloud_folder_create(request):
    if not _can_manage_cloud(
        request.user,
        CLOUD_CREATE_FOLDER_PERMISSION,
    ):
        return HttpResponseForbidden(
            "No tienes permisos para crear carpetas."
        )

    gateway = NextcloudCloudGateway()

    try:
        parent_path = gateway.normalize_path(
            request.POST.get(
                "path",
                "",
            ),
            allow_empty=True,
        )

        folder_name = request.POST.get(
            "name",
            "",
        )

        try:
            parent_snapshot = (
                snapshot_cloud_references(
                    parent_path
                )
            )
        except Exception:
            logger.exception(
                "No se pudo capturar el ámbito "
                "documental de la carpeta remota.",
                extra={
                    "actor_id": request.user.pk,
                    "parent_path": parent_path,
                },
            )

            parent_snapshot = None

        created = gateway.create_directory(
            parent_path,
            folder_name,
        )

        created_path = str(
            created.get("storage_key")
            or "/".join(
                value
                for value in (
                    parent_path,
                    created.get("name"),
                )
                if value
            )
        ).strip("/")

        try:
            registrar_operacion_cloud(
                request=request,
                accion="crear_carpeta",
                item=created,
                destination=created_path,
                snapshot=parent_snapshot,
                references_affected=0,
                url=_cloud_explorer_url(
                    created_path
                ),
            )

        except Exception:
            logger.exception(
                "La carpeta remota se creó, "
                "pero no pudo registrarse "
                "su actividad.",
                extra={
                    "actor_id": request.user.pk,
                    "created_path": created_path,
                },
            )

            messages.warning(
                request,
                (
                    "La carpeta se creó, pero "
                    "su actividad no pudo "
                    "incorporarse al panel."
                ),
            )

        messages.success(
            request,
            (
                "Carpeta creada: "
                + str(created["name"])
            ),
        )

    except CloudGatewayError as exc:
        messages.error(
            request,
            str(exc),
        )

        parent_path = str(
            request.POST.get(
                "path",
                "",
            )
            or ""
        ).strip("/")

    return redirect(
        _cloud_explorer_url(
            parent_path
        )
    )




@login_required
@require_POST
def cloud_upload_files(request):
    if not _can_manage_cloud(
        request.user,
        CLOUD_UPLOAD_FILE_PERMISSION,
    ):
        return HttpResponseForbidden(
            "No tienes permisos para subir archivos."
        )

    gateway = NextcloudCloudGateway()

    try:
        parent_path = gateway.normalize_path(
            request.POST.get("path", ""),
            allow_empty=True,
        )
    except CloudGatewayError as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            _cloud_explorer_url("")
        )

    files = request.FILES.getlist("files")

    if not files:
        messages.error(
            request,
            "No se seleccionó ningún archivo.",
        )

        return redirect(
            _cloud_explorer_url(parent_path)
        )

    try:
        team = resolve_document_team(request)
        cloud_folder = _cloud_index_folder()
    except (
        DocumentTeamResolutionError,
        CloudGatewayError,
    ) as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            _cloud_explorer_url(parent_path)
        )

    uploaded = 0
    failures = []
    reference_failures = []
    indexed_archivos = []

    for uploaded_file in files:
        try:
            item = gateway.upload_file(
                parent_path,
                uploaded_file,
            )

            uploaded += 1

            try:
                archivo, _created = (
                    upsert_cloud_uploaded_reference(
                        folder=cloud_folder,
                        item=item,
                        actor=request.user,
                        team=team,
                    )
                )

                indexed_archivos.append(archivo)

            except CloudReferenceError as exc:
                reference_failures.append(
                    (
                        f"«{uploaded_file.name}» se subió, "
                        "pero no pudo asociarse a la empresa: "
                        f"{exc}"
                    )
                )

        except CloudGatewayError as exc:
            failures.append(
                str(exc)
            )

    if indexed_archivos:
        try:
            registrar_subida_documental(
                actor=request.user,
                team=team,
                archivos=indexed_archivos,
                destino=(
                    parent_path
                    or "Archivos"
                ),
                url=_cloud_explorer_url(
                    parent_path
                ),
                storage_provider="nextcloud",
            )
        except Exception:
            logger.exception(
                "No se pudo registrar la actividad "
                "de una subida documental Nextcloud.",
                extra={
                    "actor_id": request.user.pk,
                    "team_id": team.pk,
                    "parent_path": parent_path,
                    "archivo_ids": [
                        archivo.pk
                        for archivo
                        in indexed_archivos
                    ],
                },
            )

            messages.warning(
                request,
                (
                    "Los archivos se subieron, pero "
                    "la actividad no pudo incorporarse "
                    "al panel."
                ),
            )

    if uploaded:
        messages.success(
            request,
            (
                f"Se subieron {uploaded} "
                "archivo(s) a INTASA Documents."
            ),
        )

    for failure in failures[:10]:
        messages.error(
            request,
            failure,
        )

    for failure in reference_failures[:10]:
        messages.error(
            request,
            failure,
        )

    remaining_errors = (
        max(len(failures) - 10, 0)
        + max(
            len(reference_failures) - 10,
            0,
        )
    )

    if remaining_errors:
        messages.error(
            request,
            (
                "Además, hubo "
                f"{remaining_errors} "
                "errores adicionales."
            ),
        )

    return redirect(
        _cloud_explorer_url(parent_path)
    )


