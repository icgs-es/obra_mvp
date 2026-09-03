"""
INTASA Documents · Subida completa de carpetas V1 · P1B.

Endpoints backend ocultos:

- Prevalidación JSON del manifiesto.
- Ejecución multipart por lotes.
- Sin conexión con plantillas o JavaScript visible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid

from dataclasses import replace
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.core import signing
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .activity import (
    registrar_subida_documental,
)
from .cloud_activity import (
    registrar_operacion_cloud,
    snapshot_cloud_references,
)
from .cloud_folder_upload import (
    FolderUploadInput,
    FolderUploadLimits,
    FolderUploadPlan,
    FolderUploadValidationError,
    POLICY_CANCEL,
    POLICY_RENAME,
    POLICY_REPLACE,
    POLICY_SKIP,
    SUPPORTED_POLICIES,
    _auto_rename_target,
    build_folder_upload_plan,
    execute_folder_upload,
    normalize_destination_path,
    normalize_relative_path,
)
from .cloud_gateway import (
    CloudGatewayError,
    NextcloudCloudGateway,
)
from .cloud_references import (
    CloudReferenceError,
    upsert_cloud_uploaded_reference,
)
from .cloud_views import (
    _can_manage_cloud,
    _cloud_explorer_url,
    _cloud_index_folder,
)
from .models import Archivo
from .team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)


logger = logging.getLogger(__name__)

TOKEN_SALT = (
    "archivos.cloud-folder-upload.v1"
)
TOKEN_VERSION = 1


# P3_FOLDER_UPLOAD_RBAC
FOLDER_UPLOAD_PERMISSION = (
    "archivos.upload_folder"
)


def _can_upload_cloud_folder(user) -> bool:
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.has_perm(
                FOLDER_UPLOAD_PERMISSION
            )
        )
    )


def _setting_int(
    name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    try:
        value = int(
            getattr(settings, name, default)
        )
    except (TypeError, ValueError):
        value = default

    return max(value, minimum)


def _limits() -> FolderUploadLimits:
    return FolderUploadLimits(
        max_files=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_FILES",
            5000,
        ),
        max_directories=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_DIRECTORIES",
            5000,
        ),
        max_file_size=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_FILE_SIZE",
            512 * 1024 * 1024,
        ),
        max_total_size=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_TOTAL_SIZE",
            10 * 1024 * 1024 * 1024,
        ),
        max_depth=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_DEPTH",
            20,
        ),
        max_name_length=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_NAME_LENGTH",
            255,
        ),
        max_path_length=_setting_int(
            "INTASA_DOCUMENTS_FOLDER_UPLOAD_MAX_PATH_LENGTH",
            1024,
        ),
    )


def _batch_file_limit() -> int:
    configured = _setting_int(
        "INTASA_DOCUMENTS_FOLDER_UPLOAD_BATCH_FILES",
        50,
    )

    django_limit = getattr(
        settings,
        "DATA_UPLOAD_MAX_NUMBER_FILES",
        100,
    )

    try:
        django_limit = int(django_limit)
    except (TypeError, ValueError):
        django_limit = 100

    return max(
        min(configured, django_limit, 100),
        1,
    )


def _manifest_bytes_limit() -> int:
    return _setting_int(
        "INTASA_DOCUMENTS_FOLDER_UPLOAD_MANIFEST_BYTES",
        2 * 1024 * 1024,
    )


def _token_max_age() -> int:
    return _setting_int(
        "INTASA_DOCUMENTS_FOLDER_UPLOAD_TOKEN_MAX_AGE",
        6 * 60 * 60,
    )


def _join_path(*parts: str) -> str:
    return "/".join(
        str(part).strip("/")
        for part in parts
        if str(part or "").strip("/")
    )


def _parent_and_name(
    path: str,
) -> tuple[str, str]:
    parsed = PurePosixPath(path)
    parent = str(parsed.parent)

    if parent == ".":
        parent = ""

    return parent, parsed.name


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _manifest_digest(
    manifest: dict[str, Any],
) -> str:
    return hashlib.sha256(
        _canonical_json(manifest).encode("utf-8")
    ).hexdigest()


def _bool_value(value: Any) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "on",
    }


def _json_error(
    code: str,
    message: str,
    *,
    status: int = 400,
    details: Any = None,
) -> JsonResponse:
    payload = {
        "ok": False,
        "error": {
            "code": str(code),
            "message": str(message),
        },
    }

    if details is not None:
        payload["error"]["details"] = details

    response = JsonResponse(
        payload,
        status=status,
        json_dumps_params={
            "ensure_ascii": False,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


def _json_success(
    payload: dict[str, Any],
    *,
    status: int = 200,
) -> JsonResponse:
    response = JsonResponse(
        {
            "ok": True,
            **payload,
        },
        status=status,
        json_dumps_params={
            "ensure_ascii": False,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


def _require_manager(request):
    if not _can_upload_cloud_folder(request.user):
        return _json_error(
            "permission_denied",
            (
                "No tienes permisos para subir "
                "carpetas completas."
            ),
            status=403,
        )

    return None


def _parse_json_request(
    request,
) -> dict[str, Any]:
    raw = request.body or b""

    if len(raw) > _manifest_bytes_limit():
        raise FolderUploadValidationError(
            "manifest_too_large",
            "El manifiesto supera el tamaño permitido.",
        )

    try:
        value = json.loads(
            raw.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise FolderUploadValidationError(
            "invalid_json",
            "La petición JSON no es válida.",
        ) from exc

    if not isinstance(value, dict):
        raise FolderUploadValidationError(
            "invalid_payload",
            "La petición debe contener un objeto JSON.",
        )

    return value


def _normalize_manifest_directories(
    values,
    *,
    limits: FolderUploadLimits,
) -> list[str]:
    if values in (None, ""):
        return []

    if not isinstance(values, list):
        raise FolderUploadValidationError(
            "invalid_directories",
            "La lista de carpetas no es válida.",
        )

    normalized = {
        normalize_relative_path(
            value,
            limits=limits,
            require_child=False,
        )
        for value in values
    }

    return sorted(
        normalized,
        key=lambda path: (
            path.count("/"),
            path.casefold(),
        ),
    )


def _manifest_inputs(
    values,
) -> list[FolderUploadInput]:
    if not isinstance(values, list):
        raise FolderUploadValidationError(
            "invalid_files",
            "La lista de archivos no es válida.",
        )

    result = []

    for value in values:
        if not isinstance(value, dict):
            raise FolderUploadValidationError(
                "invalid_file_descriptor",
                "Un archivo del manifiesto no es válido.",
            )

        relative_path = (
            value.get("relative_path")
            or value.get("path")
            or ""
        )

        try:
            size = int(value.get("size"))
        except (TypeError, ValueError) as exc:
            raise FolderUploadValidationError(
                "invalid_size",
                "El tamaño declarado no es válido.",
                path=str(relative_path or ""),
            ) from exc

        result.append(
            FolderUploadInput(
                uploaded_file=SimpleNamespace(
                    name=PurePosixPath(
                        str(relative_path or "")
                        .replace("\\", "/")
                    ).name,
                    size=size,
                ),
                relative_path=str(
                    relative_path or ""
                ),
            )
        )

    return result


def _validate_destination_scope(
    destination_path: str,
    team,
) -> str:
    snapshot = snapshot_cloud_references(
        destination_path
    )

    assigned = {
        int(value)
        for value in snapshot.get(
            "assigned_team_ids",
            [],
        )
        if value
    }

    foreign = sorted(
        value
        for value in assigned
        if value != team.pk
    )

    if foreign:
        raise FolderUploadValidationError(
            "destination_team_conflict",
            (
                "La carpeta de destino contiene "
                "documentos asociados a otra empresa."
            ),
            path=destination_path,
        )

    if snapshot.get("unclassified_count"):
        return (
            "La carpeta contiene referencias sin "
            "empresa clasificada. Los nuevos archivos "
            "se asociarán a la empresa seleccionada."
        )

    return ""


def _build_preflight_manifest(
    *,
    payload: dict[str, Any],
    gateway,
) -> tuple[
    dict[str, Any],
    FolderUploadPlan,
    bool,
]:
    limits = _limits()

    policy = str(
        payload.get("policy")
        or POLICY_SKIP
    ).strip().lower()

    if policy not in SUPPORTED_POLICIES:
        raise FolderUploadValidationError(
            "invalid_policy",
            "La política de colisiones no es válida.",
        )

    allow_replace = _bool_value(
        payload.get("allow_replace")
    )

    if (
        policy == POLICY_REPLACE
        and not allow_replace
    ):
        raise FolderUploadValidationError(
            "replace_not_authorized",
            (
                "Reemplazar requiere una autorización "
                "explícita."
            ),
        )

    destination = gateway.normalize_path(
        payload.get("path", ""),
        allow_empty=True,
    )

    declared_directories = (
        _normalize_manifest_directories(
            payload.get("directories", []),
            limits=limits,
        )
    )

    plan = build_folder_upload_plan(
        _manifest_inputs(
            payload.get("files", [])
        ),
        destination_path=destination,
        gateway=gateway,
        declared_directories=(
            declared_directories
        ),
        limits=limits,
    )

    conflict_by_path = {
        conflict.path: conflict.kind
        for conflict in plan.conflicts
    }

    expected_directories = set(
        plan.directories
    )

    blocking_directories = [
        {
            "path": path,
            "kind": conflict_by_path[path],
        }
        for path in sorted(
            expected_directories
            & set(conflict_by_path)
        )
        if conflict_by_path[path]
        not in {"directory"}
    ]

    if blocking_directories:
        raise FolderUploadValidationError(
            "directory_blocked",
            (
                "Una ruta necesaria para crear la "
                "estructura está ocupada por un archivo "
                "o no pudo clasificarse con seguridad."
            ),
            path=blocking_directories[0]["path"],
        )

    reserved_targets: set[str] = set()
    manifest_files = []
    file_collision_count = 0

    for planned in plan.files:
        original_target = planned.target_path
        collision_kind = conflict_by_path.get(
            original_target,
            "",
        )

        target_path = original_target

        if collision_kind:
            file_collision_count += 1

        if (
            policy == POLICY_REPLACE
            and collision_kind
            not in {"", "file"}
        ):
            raise FolderUploadValidationError(
                "replace_target_not_file",
                (
                    "Reemplazar solo puede aplicarse "
                    "sobre archivos existentes."
                ),
                path=original_target,
            )

        if (
            policy == POLICY_RENAME
            and collision_kind
        ):
            target_path = _auto_rename_target(
                gateway,
                original_target,
                reserved_paths=reserved_targets,
            )

        reserved_targets.add(target_path)

        manifest_files.append({
            "relative_path": (
                planned.relative_path
            ),
            "size": planned.size,
            "original_target_path": (
                original_target
            ),
            "target_path": target_path,
            "collision_kind": (
                collision_kind
            ),
        })

    can_execute = not (
        policy == POLICY_CANCEL
        and file_collision_count > 0
    )

    manifest = {
        "version": TOKEN_VERSION,
        "destination_path": (
            plan.destination_path
        ),
        "root_name": plan.root_name,
        "policy": policy,
        "allow_replace": allow_replace,
        "declared_directories": (
            declared_directories
        ),
        "directories": list(
            plan.directories
        ),
        "files": manifest_files,
        "total_size": plan.total_size,
        "files_count": plan.files_count,
        "directories_count": (
            plan.directories_count
        ),
    }

    return manifest, plan, can_execute


def _load_token(
    token: str,
) -> dict[str, Any]:
    try:
        value = signing.loads(
            token,
            salt=TOKEN_SALT,
            max_age=_token_max_age(),
        )
    except signing.SignatureExpired as exc:
        raise FolderUploadValidationError(
            "expired_token",
            "La autorización de subida ha caducado.",
        ) from exc
    except signing.BadSignature as exc:
        raise FolderUploadValidationError(
            "invalid_token",
            "La autorización de subida no es válida.",
        ) from exc

    if (
        not isinstance(value, dict)
        or value.get("version")
        != TOKEN_VERSION
    ):
        raise FolderUploadValidationError(
            "invalid_token",
            "La autorización no tiene un formato válido.",
        )

    return value


def _parse_signed_manifest(
    raw_value: str,
    *,
    token_data: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    encoded = str(raw_value or "")

    if not encoded:
        raise FolderUploadValidationError(
            "missing_manifest",
            "No se recibió el manifiesto firmado.",
        )

    if (
        len(encoded.encode("utf-8"))
        > _manifest_bytes_limit()
    ):
        raise FolderUploadValidationError(
            "manifest_too_large",
            "El manifiesto supera el tamaño permitido.",
        )

    try:
        manifest = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise FolderUploadValidationError(
            "invalid_manifest",
            "El manifiesto no es JSON válido.",
        ) from exc

    if not isinstance(manifest, dict):
        raise FolderUploadValidationError(
            "invalid_manifest",
            "El manifiesto debe ser un objeto.",
        )

    if (
        _manifest_digest(manifest)
        != token_data.get("manifest_digest")
    ):
        raise FolderUploadValidationError(
            "manifest_signature_mismatch",
            (
                "El manifiesto no coincide con "
                "la prevalidación."
            ),
        )

    if (
        manifest.get("version")
        != TOKEN_VERSION
    ):
        raise FolderUploadValidationError(
            "invalid_manifest_version",
            "La versión del manifiesto no es válida.",
        )

    destination = str(
        token_data.get("destination_path")
        or ""
    ).strip("/")

    policy = str(
        token_data.get("policy")
        or ""
    )

    if (
        str(
            manifest.get("destination_path")
            or ""
        ).strip("/")
        != destination
    ):
        raise FolderUploadValidationError(
            "destination_changed",
            "La carpeta de destino fue modificada.",
        )

    if manifest.get("policy") != policy:
        raise FolderUploadValidationError(
            "policy_changed",
            "La política de colisiones fue modificada.",
        )

    limits = _limits()
    root_name = normalize_relative_path(
        manifest.get("root_name"),
        limits=limits,
        require_child=False,
    )

    if "/" in root_name:
        raise FolderUploadValidationError(
            "invalid_root",
            "La carpeta raíz no es válida.",
        )

    root_target = _join_path(
        destination,
        root_name,
    )

    files = manifest.get("files")

    if not isinstance(files, list):
        raise FolderUploadValidationError(
            "invalid_manifest_files",
            "La lista firmada de archivos no es válida.",
        )

    file_map = {}

    for entry in files:
        if not isinstance(entry, dict):
            raise FolderUploadValidationError(
                "invalid_manifest_file",
                "Un archivo firmado no es válido.",
            )

        relative_path = normalize_relative_path(
            entry.get("relative_path"),
            limits=limits,
        )

        if relative_path in file_map:
            raise FolderUploadValidationError(
                "duplicate_manifest_path",
                (
                    "El manifiesto firmado contiene "
                    "rutas duplicadas."
                ),
                path=relative_path,
            )

        try:
            size = int(entry.get("size"))
        except (TypeError, ValueError) as exc:
            raise FolderUploadValidationError(
                "invalid_size",
                "El tamaño firmado no es válido.",
                path=relative_path,
            ) from exc

        expected_original = _join_path(
            destination,
            relative_path,
        )

        original_target = (
            normalize_destination_path(
                entry.get(
                    "original_target_path"
                ),
                limits=limits,
            )
        )

        target_path = (
            normalize_destination_path(
                entry.get("target_path"),
                limits=limits,
            )
        )

        if original_target != expected_original:
            raise FolderUploadValidationError(
                "original_target_changed",
                (
                    "La ruta original firmada no "
                    "coincide con el manifiesto."
                ),
                path=relative_path,
            )

        if not (
            target_path == root_target
            or target_path.startswith(
                root_target + "/"
            )
        ):
            raise FolderUploadValidationError(
                "target_outside_root",
                (
                    "La ruta de destino queda fuera "
                    "de la carpeta seleccionada."
                ),
                path=target_path,
            )

        original_parent, _ = (
            _parent_and_name(original_target)
        )
        target_parent, _ = (
            _parent_and_name(target_path)
        )

        if policy == POLICY_RENAME:
            if target_parent != original_parent:
                raise FolderUploadValidationError(
                    "rename_parent_changed",
                    (
                        "El renombrado no puede cambiar "
                        "la carpeta de destino."
                    ),
                    path=target_path,
                )
        elif target_path != original_target:
            raise FolderUploadValidationError(
                "target_changed",
                "La ruta de destino fue modificada.",
                path=target_path,
            )

        normalized_entry = {
            **entry,
            "relative_path": relative_path,
            "size": size,
            "original_target_path": (
                original_target
            ),
            "target_path": target_path,
        }

        file_map[relative_path] = (
            normalized_entry
        )

    declared_directories = (
        _normalize_manifest_directories(
            manifest.get(
                "declared_directories",
                [],
            ),
            limits=limits,
        )
    )

    manifest[
        "declared_directories"
    ] = declared_directories

    return manifest, file_map


def _parse_json_list_field(
    request,
    name: str,
) -> list:
    raw = str(
        request.POST.get(name, "")
        or ""
    ).strip()

    if not raw:
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FolderUploadValidationError(
            f"invalid_{name}",
            f"El campo {name} no contiene JSON válido.",
        ) from exc

    if not isinstance(value, list):
        raise FolderUploadValidationError(
            f"invalid_{name}",
            f"El campo {name} debe ser una lista.",
        )

    return value


@never_cache
@csrf_protect
@require_POST
def cloud_folder_upload_preflight(
    request,
):
    permission_error = _require_manager(
        request
    )

    if permission_error is not None:
        return permission_error

    try:
        payload = _parse_json_request(
            request
        )

        team = resolve_document_team(
            request
        )

        gateway = NextcloudCloudGateway()

        manifest, plan, can_execute = (
            _build_preflight_manifest(
                payload=payload,
                gateway=gateway,
            )
        )

        scope_warning = (
            _validate_destination_scope(
                plan.destination_path,
                team,
            )
        )

        operation_id = uuid.uuid4().hex
        digest = _manifest_digest(
            manifest
        )

        token = ""

        if can_execute:
            token = signing.dumps(
                {
                    "version": TOKEN_VERSION,
                    "operation_id": (
                        operation_id
                    ),
                    "user_id": request.user.pk,
                    "team_id": team.pk,
                    "destination_path": (
                        plan.destination_path
                    ),
                    "root_name": (
                        plan.root_name
                    ),
                    "policy": (
                        manifest["policy"]
                    ),
                    "allow_replace": (
                        manifest[
                            "allow_replace"
                        ]
                    ),
                    "manifest_digest": digest,
                },
                salt=TOKEN_SALT,
                compress=True,
            )

        return _json_success({
            "operation_id": operation_id,
            "can_execute": can_execute,
            "token": token,
            "token_max_age_seconds": (
                _token_max_age()
            ),
            "batch_file_limit": (
                _batch_file_limit()
            ),
            "team": {
                "id": team.pk,
                "name": str(team),
            },
            "summary": {
                "root_name": (
                    plan.root_name
                ),
                "files": (
                    plan.files_count
                ),
                "directories": (
                    plan.directories_count
                ),
                "total_size": (
                    plan.total_size
                ),
                "conflicts": len(
                    plan.conflicts
                ),
                "policy": (
                    manifest["policy"]
                ),
            },
            "conflicts": [
                {
                    "path": conflict.path,
                    "kind": conflict.kind,
                }
                for conflict in plan.conflicts
            ],
            "scope_warning": (
                scope_warning
            ),
            "manifest": manifest,
        })

    except (
        FolderUploadValidationError,
        DocumentTeamResolutionError,
        CloudGatewayError,
    ) as exc:
        code = getattr(
            exc,
            "code",
            "preflight_failed",
        )

        return _json_error(
            code,
            str(exc),
            status=400,
        )


@never_cache
@csrf_protect
@require_POST
def cloud_folder_upload_execute(
    request,
):
    permission_error = _require_manager(
        request
    )

    if permission_error is not None:
        return permission_error

    try:
        token_data = _load_token(
            request.POST.get("token", "")
        )

        if (
            int(
                token_data.get("user_id")
                or 0
            )
            != request.user.pk
        ):
            return _json_error(
                "token_user_mismatch",
                (
                    "La autorización pertenece "
                    "a otro usuario."
                ),
                status=403,
            )

        team = resolve_document_team(
            request
        )

        if (
            int(
                token_data.get("team_id")
                or 0
            )
            != team.pk
        ):
            return _json_error(
                "token_team_mismatch",
                (
                    "La empresa activa no coincide "
                    "con la prevalidación."
                ),
                status=403,
            )

        manifest, file_map = (
            _parse_signed_manifest(
                request.POST.get(
                    "manifest",
                    "",
                ),
                token_data=token_data,
            )
        )

        destination = str(
            token_data.get(
                "destination_path",
                "",
            )
            or ""
        ).strip("/")

        _validate_destination_scope(
            destination,
            team,
        )

        uploaded_files = (
            request.FILES.getlist("files")
        )
        relative_paths = (
            request.POST.getlist("relpath")
        )

        if (
            len(uploaded_files)
            != len(relative_paths)
        ):
            raise FolderUploadValidationError(
                "batch_pair_mismatch",
                (
                    "Cada archivo debe incluir "
                    "su ruta relativa."
                ),
            )

        if (
            len(uploaded_files)
            > _batch_file_limit()
        ):
            raise FolderUploadValidationError(
                "batch_file_limit_exceeded",
                (
                    "El lote supera el máximo "
                    "de archivos permitido."
                ),
            )

        limits = _limits()
        batch_inputs = []
        seen_paths = set()

        for uploaded_file, raw_path in zip(
            uploaded_files,
            relative_paths,
        ):
            relative_path = (
                normalize_relative_path(
                    raw_path,
                    limits=limits,
                )
            )

            if relative_path in seen_paths:
                raise FolderUploadValidationError(
                    "duplicate_batch_path",
                    (
                        "El lote contiene la misma "
                        "ruta más de una vez."
                    ),
                    path=relative_path,
                )

            seen_paths.add(relative_path)

            signed_entry = file_map.get(
                relative_path
            )

            if signed_entry is None:
                raise FolderUploadValidationError(
                    "unsigned_file",
                    (
                        "El archivo no pertenece "
                        "al manifiesto prevalidado."
                    ),
                    path=relative_path,
                )

            actual_size = int(
                getattr(
                    uploaded_file,
                    "size",
                    -1,
                )
            )

            if (
                actual_size
                != signed_entry["size"]
            ):
                raise FolderUploadValidationError(
                    "file_size_changed",
                    (
                        "El tamaño recibido no coincide "
                        "con el manifiesto."
                    ),
                    path=relative_path,
                )

            batch_inputs.append(
                FolderUploadInput(
                    uploaded_file=uploaded_file,
                    relative_path=(
                        relative_path
                    ),
                )
            )

        batch_directories = (
            _normalize_manifest_directories(
                _parse_json_list_field(
                    request,
                    "directories",
                ),
                limits=limits,
            )
        )

        allowed_declared_directories = set(
            manifest.get(
                "declared_directories",
                [],
            )
        )

        unsigned_directories = [
            directory
            for directory
            in batch_directories
            if directory
            not in allowed_declared_directories
        ]

        if unsigned_directories:
            raise FolderUploadValidationError(
                "unsigned_directory",
                (
                    "Una carpeta del lote no pertenece "
                    "al manifiesto prevalidado."
                ),
                path=unsigned_directories[0],
            )

        finalize = _bool_value(
            request.POST.get("finalize")
        )

        if (
            not batch_inputs
            and not batch_directories
            and not finalize
        ):
            raise FolderUploadValidationError(
                "empty_batch",
                "El lote no contiene elementos.",
            )

        gateway = NextcloudCloudGateway()
        cloud_folder = _cloud_index_folder()

        if batch_inputs or batch_directories:
            batch_plan = (
                build_folder_upload_plan(
                    batch_inputs,
                    destination_path=(
                        destination
                    ),
                    declared_directories=(
                        batch_directories
                    ),
                    limits=limits,
                )
            )

            replaced_files = []

            for planned in batch_plan.files:
                signed_entry = file_map[
                    planned.relative_path
                ]

                target_path = (
                    signed_entry[
                        "target_path"
                    ]
                )

                parent_path, filename = (
                    _parent_and_name(
                        target_path
                    )
                )

                replaced_files.append(
                    replace(
                        planned,
                        target_path=(
                            target_path
                        ),
                        parent_path=(
                            parent_path
                        ),
                        filename=filename,
                    )
                )

            batch_plan = FolderUploadPlan(
                destination_path=(
                    batch_plan
                    .destination_path
                ),
                root_name=(
                    batch_plan.root_name
                ),
                directories=(
                    batch_plan.directories
                ),
                files=tuple(
                    replaced_files
                ),
                total_size=(
                    batch_plan.total_size
                ),
                conflicts=(),
                limits=batch_plan.limits,
            )
        else:
            batch_plan = FolderUploadPlan(
                destination_path=destination,
                root_name=str(
                    manifest.get(
                        "root_name",
                        "",
                    )
                ),
                directories=(),
                files=(),
                total_size=0,
                conflicts=(),
                limits=limits,
            )

        indexed_archivos = []
        reference_errors = []

        def reference_writer(
            planned,
            item,
            final_target,
        ):
            try:
                item = dict(item or {})
                item["storage_key"] = (
                    final_target
                )

                archivo, _created = (
                    upsert_cloud_uploaded_reference(
                        folder=cloud_folder,
                        item=item,
                        actor=request.user,
                        team=team,
                    )
                )

                indexed_archivos.append(
                    archivo
                )

                return archivo

            except CloudReferenceError as exc:
                reference_errors.append({
                    "relative_path": (
                        planned.relative_path
                    ),
                    "target_path": (
                        final_target
                    ),
                    "error": str(exc),
                })

                raise

        policy = str(
            token_data.get("policy")
            or POLICY_SKIP
        )

        effective_policy = (
            POLICY_SKIP
            if policy == POLICY_RENAME
            else policy
        )

        execution = execute_folder_upload(
            batch_plan,
            gateway=gateway,
            policy=effective_policy,
            allow_replace=bool(
                token_data.get(
                    "allow_replace"
                )
            ),
            reference_writer=(
                reference_writer
            ),
        )

        execution_payload = (
            execution.as_dict()
        )

        for item in execution_payload[
            "files"
        ]:
            signed_entry = file_map.get(
                item["relative_path"]
            )

            if signed_entry is None:
                continue

            item["original_target_path"] = (
                signed_entry[
                    "original_target_path"
                ]
            )
            item["collision_policy"] = (
                policy
            )

            if (
                policy == POLICY_RENAME
                and item["target_path"]
                != item[
                    "original_target_path"
                ]
                and item["status"]
                == "uploaded"
            ):
                item["status"] = "renamed"

        indexed_ids = sorted({
            archivo.pk
            for archivo in indexed_archivos
            if archivo.pk
        })

        activity_registered = False
        activity_error = ""

        if finalize:
            requested_ids = (
                _parse_json_list_field(
                    request,
                    "activity_file_ids",
                )
            )

            normalized_ids = set(
                indexed_ids
            )

            for value in requested_ids:
                try:
                    normalized_ids.add(
                        int(value)
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    raise (
                        FolderUploadValidationError(
                            "invalid_activity_file_id",
                            (
                                "La lista de referencias "
                                "de actividad no es válida."
                            ),
                        )
                    )

            allowed_paths = {
                entry["target_path"]
                for entry in file_map.values()
            }

            activity_archivos = list(
                Archivo.objects
                .filter(
                    pk__in=normalized_ids,
                    team=team,
                    storage_provider="nextcloud",
                    storage_key__in=allowed_paths,
                )
                .order_by("pk")
            )

            found_ids = {
                archivo.pk
                for archivo
                in activity_archivos
            }

            if (
                normalized_ids
                and found_ids
                != normalized_ids
            ):
                activity_error = (
                    "Alguna referencia solicitada "
                    "no pertenece a la operación."
                )

            else:
                try:
                    try:
                        folders_total = int(
                            request.POST.get(
                                "created_folders_total",
                                len(
                                    execution
                                    .created_folders
                                ),
                            )
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        folders_total = len(
                            execution
                            .created_folders
                        )

                    folders_total = max(
                        min(
                            folders_total,
                            len(
                                manifest.get(
                                    "directories",
                                    [],
                                )
                            ),
                        ),
                        0,
                    )

                    root_destination = (
                        _join_path(
                            destination,
                            manifest.get(
                                "root_name",
                                "",
                            ),
                        )
                    )

                    # P3_FOLDER_UPLOAD_FINAL_AUDIT
                    operation_id = str(
                        token_data.get(
                            "operation_id"
                        )
                        or ""
                    )

                    declared_files = len(
                        manifest.get(
                            "files",
                            [],
                        )
                    )

                    declared_directories = len(
                        manifest.get(
                            "directories",
                            [],
                        )
                    )

                    declared_total_size = sum(
                        int(
                            entry.get(
                                "size",
                                0,
                            )
                            or 0
                        )
                        for entry
                        in manifest.get(
                            "files",
                            [],
                        )
                        if isinstance(
                            entry,
                            dict,
                        )
                    )

                    indexed_references = len(
                        activity_archivos
                    )

                    unindexed_files = max(
                        declared_files
                        - indexed_references,
                        0,
                    )

                    audit_metadata = {
                        "root_name": (
                            manifest.get(
                                "root_name",
                                "",
                            )
                        ),
                        "declared_files": (
                            declared_files
                        ),
                        "declared_directories": (
                            declared_directories
                        ),
                        "declared_total_size": (
                            declared_total_size
                        ),
                        "indexed_references": (
                            indexed_references
                        ),
                        "unindexed_files": (
                            unindexed_files
                        ),
                        "reference_coverage_complete": (
                            unindexed_files == 0
                        ),
                        "finalized": True,
                        "audit_result": (
                            "complete"
                            if unindexed_files == 0
                            else "completed_with_unindexed_files"
                        ),
                    }

                    if activity_archivos:
                        registrar_subida_documental(
                            actor=request.user,
                            team=team,
                            archivos=(
                                activity_archivos
                            ),
                            destino=(
                                root_destination
                                or "Archivos"
                            ),
                            url=(
                                _cloud_explorer_url(
                                    root_destination
                                )
                            ),
                            storage_provider=(
                                "nextcloud"
                            ),
                            carpetas_creadas=(
                                folders_total
                            ),
                            operation_id=(
                                operation_id
                            ),
                            policy=policy,
                            audit_metadata=(
                                audit_metadata
                            ),
                            diferir_hasta_commit=(
                                False
                            ),
                        )

                        activity_registered = True

                    elif folders_total:
                        registrar_operacion_cloud(
                            request=request,
                            accion=(
                                "crear_carpeta"
                            ),
                            item={
                                "name": (
                                    manifest.get(
                                        "root_name",
                                        "",
                                    )
                                ),
                                "is_folder": True,
                            },
                            destination=(
                                root_destination
                            ),
                            explicit_team=team,
                            operation_id=(
                                operation_id
                            ),
                            references_affected=0,
                            url=(
                                _cloud_explorer_url(
                                    root_destination
                                )
                            ),
                        )

                        activity_registered = True

                except Exception as exc:
                    logger.exception(
                        (
                            "La subida de carpeta terminó, "
                            "pero falló su actividad."
                        ),
                        extra={
                            "actor_id": (
                                request.user.pk
                            ),
                            "team_id": team.pk,
                            "operation_id": (
                                token_data.get(
                                    "operation_id"
                                )
                            ),
                        },
                    )

                    activity_error = str(exc)

        return _json_success({
            "operation_id": (
                token_data.get(
                    "operation_id"
                )
            ),
            "batch_file_limit": (
                _batch_file_limit()
            ),
            "result": execution_payload,
            "indexed_file_ids": indexed_ids,
            "reference_errors": (
                reference_errors
            ),
            "finalized": finalize,
            "activity_registered": (
                activity_registered
            ),
            "activity_error": (
                activity_error
            ),
        })

    except (
        FolderUploadValidationError,
        DocumentTeamResolutionError,
        CloudGatewayError,
    ) as exc:
        code = getattr(
            exc,
            "code",
            "execution_failed",
        )

        return _json_error(
            code,
            str(exc),
            status=400,
        )
