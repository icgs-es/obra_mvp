"""
INTASA Documents · Subida completa de carpetas V1 · P1A.

Servicio backend independiente de las vistas y plantillas.

En esta fase:

- No registra URLs.
- No modifica el explorador visible.
- No realiza operaciones durante la importación.
- No conoce credenciales de Nextcloud.
- Opera contra el contrato existente de NextcloudCloudGateway.
- Permite validar el manifiesto antes de modificar almacenamiento.
- Procesa errores por archivo sin cancelar todo el lote.
"""

from __future__ import annotations

import re
import uuid

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence


POLICY_SKIP = "skip"
POLICY_RENAME = "rename"
POLICY_REPLACE = "replace"
POLICY_CANCEL = "cancel"

SUPPORTED_POLICIES = frozenset({
    POLICY_SKIP,
    POLICY_RENAME,
    POLICY_REPLACE,
    POLICY_CANCEL,
})

SUCCESS_STATUSES = frozenset({
    "uploaded",
    "renamed",
    "replaced",
})


class FolderUploadError(Exception):
    """Error controlado de la operación de subida de carpetas."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str = "",
    ) -> None:
        self.code = str(code)
        self.message = str(message)
        self.path = str(path or "")

        text = f"{self.code}: {self.message}"

        if self.path:
            text += f" [{self.path}]"

        super().__init__(text)


class FolderUploadValidationError(FolderUploadError):
    """El manifiesto o alguno de sus elementos no es seguro."""


@dataclass(frozen=True)
class FolderUploadLimits:
    max_files: int = 5000
    max_directories: int = 5000
    max_file_size: int = 512 * 1024 * 1024
    max_total_size: int = 10 * 1024 * 1024 * 1024
    max_depth: int = 20
    max_name_length: int = 255
    max_path_length: int = 1024


@dataclass(frozen=True)
class FolderUploadInput:
    uploaded_file: Any
    relative_path: str


@dataclass(frozen=True)
class FolderUploadConflict:
    path: str
    kind: str


@dataclass(frozen=True)
class PlannedFolderFile:
    uploaded_file: Any = field(compare=False, repr=False)
    relative_path: str
    target_path: str
    parent_path: str
    filename: str
    size: int


@dataclass(frozen=True)
class FolderUploadPlan:
    destination_path: str
    root_name: str
    directories: tuple[str, ...]
    files: tuple[PlannedFolderFile, ...]
    total_size: int
    conflicts: tuple[FolderUploadConflict, ...]
    limits: FolderUploadLimits

    @property
    def files_count(self) -> int:
        return len(self.files)

    @property
    def directories_count(self) -> int:
        return len(self.directories)

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination_path": self.destination_path,
            "root_name": self.root_name,
            "directories": list(self.directories),
            "files_count": self.files_count,
            "directories_count": self.directories_count,
            "total_size": self.total_size,
            "conflicts": [
                asdict(conflict)
                for conflict in self.conflicts
            ],
            "limits": asdict(self.limits),
        }


@dataclass(frozen=True)
class FolderUploadFileResult:
    relative_path: str
    target_path: str
    status: str
    size: int
    error_code: str = ""
    error: str = ""
    reference_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FolderUploadExecutionResult:
    policy: str
    root_name: str
    total_files: int
    total_size: int
    created_folders: list[str] = field(default_factory=list)
    reused_folders: list[str] = field(default_factory=list)
    file_results: list[FolderUploadFileResult] = field(
        default_factory=list
    )
    cancelled: bool = False

    @property
    def uploaded_files(self) -> int:
        return sum(
            item.status in SUCCESS_STATUSES
            for item in self.file_results
        )

    @property
    def skipped_files(self) -> int:
        return sum(
            item.status == "skipped"
            for item in self.file_results
        )

    @property
    def error_files(self) -> int:
        return sum(
            item.status == "error"
            for item in self.file_results
        )

    @property
    def processed_files(self) -> int:
        return len(self.file_results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "root_name": self.root_name,
            "total_files": self.total_files,
            "total_size": self.total_size,
            "created_folders": list(self.created_folders),
            "reused_folders": list(self.reused_folders),
            "uploaded_files": self.uploaded_files,
            "skipped_files": self.skipped_files,
            "error_files": self.error_files,
            "processed_files": self.processed_files,
            "cancelled": self.cancelled,
            "files": [
                item.as_dict()
                for item in self.file_results
            ],
        }


_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:")


def _join_path(*parts: str) -> str:
    return "/".join(
        str(part).strip("/")
        for part in parts
        if str(part or "").strip("/")
    )


def _parent_and_name(path: str) -> tuple[str, str]:
    parsed = PurePosixPath(path)
    parent = str(parsed.parent)

    if parent == ".":
        parent = ""

    return parent, parsed.name


def _reject(
    code: str,
    message: str,
    *,
    path: str,
) -> None:
    raise FolderUploadValidationError(
        code,
        message,
        path=path,
    )


def normalize_relative_path(
    value: Any,
    *,
    limits: FolderUploadLimits,
    require_child: bool = True,
) -> str:
    """
    Normaliza una ruta procedente de webkitRelativePath o manifiesto.

    No permite:

    - rutas absolutas;
    - letras de unidad;
    - componentes vacíos;
    - "." o "..";
    - caracteres de control;
    - superar límites configurados.
    """

    raw = str(value or "")

    if not raw:
        _reject(
            "empty_path",
            "La ruta relativa está vacía.",
            path=raw,
        )

    if "\x00" in raw:
        _reject(
            "null_byte",
            "La ruta contiene un byte nulo.",
            path=raw,
        )

    raw = raw.replace("\\", "/")

    if raw.startswith("/") or _DRIVE_PATH_RE.match(raw):
        _reject(
            "absolute_path",
            "No se permiten rutas absolutas.",
            path=raw,
        )

    parts = raw.split("/")

    if require_child and len(parts) < 2:
        _reject(
            "missing_root_folder",
            "La ruta debe incluir carpeta raíz y archivo.",
            path=raw,
        )

    for part in parts:
        if part in {"", ".", ".."}:
            _reject(
                "invalid_component",
                "La ruta contiene componentes no permitidos.",
                path=raw,
            )

        if any(ord(character) < 32 for character in part):
            _reject(
                "control_character",
                "El nombre contiene caracteres de control.",
                path=raw,
            )

        if len(part) > limits.max_name_length:
            _reject(
                "name_too_long",
                "Un nombre supera la longitud permitida.",
                path=raw,
            )

    if len(parts) > limits.max_depth:
        _reject(
            "depth_exceeded",
            "La ruta supera la profundidad permitida.",
            path=raw,
        )

    normalized = "/".join(parts)

    if len(normalized) > limits.max_path_length:
        _reject(
            "path_too_long",
            "La ruta supera la longitud permitida.",
            path=normalized,
        )

    return normalized


def normalize_destination_path(
    value: Any,
    *,
    limits: FolderUploadLimits,
) -> str:
    raw = str(value or "").strip()

    if raw in {"", "/"}:
        return ""

    return normalize_relative_path(
        raw,
        limits=limits,
        require_child=False,
    )


def _coerce_input(item: Any) -> FolderUploadInput:
    if isinstance(item, FolderUploadInput):
        return item

    if isinstance(item, Mapping):
        return FolderUploadInput(
            uploaded_file=item.get("uploaded_file")
            or item.get("file"),
            relative_path=str(
                item.get("relative_path")
                or item.get("relpath")
                or ""
            ),
        )

    if (
        isinstance(item, Sequence)
        and not isinstance(item, (str, bytes, bytearray))
        and len(item) == 2
    ):
        return FolderUploadInput(
            uploaded_file=item[0],
            relative_path=str(item[1] or ""),
        )

    raise FolderUploadValidationError(
        "invalid_manifest_item",
        "El elemento del manifiesto no tiene un formato válido.",
    )


def _uploaded_size(uploaded_file: Any, path: str) -> int:
    if uploaded_file is None:
        _reject(
            "missing_file",
            "No se recibió el archivo asociado.",
            path=path,
        )

    size = getattr(uploaded_file, "size", None)

    if size is None:
        _reject(
            "missing_size",
            "No se pudo determinar el tamaño del archivo.",
            path=path,
        )

    try:
        normalized_size = int(size)
    except (TypeError, ValueError):
        _reject(
            "invalid_size",
            "El tamaño del archivo no es válido.",
            path=path,
        )

    if normalized_size < 0:
        _reject(
            "invalid_size",
            "El tamaño del archivo no puede ser negativo.",
            path=path,
        )

    return normalized_size


def _gateway_item_kind(
    gateway: Any,
    path: str,
) -> str:
    getter = getattr(gateway, "get_item", None)

    if not callable(getter):
        return "unknown"

    try:
        item = getter(path)
    except Exception:
        return "unknown"

    if not isinstance(item, Mapping):
        return "unknown"

    if item.get("is_folder") is True:
        return "directory"

    if item.get("is_dir") is True:
        return "directory"

    if item.get("is_directory") is True:
        return "directory"

    item_type = str(
        item.get("type")
        or item.get("kind")
        or ""
    ).lower()

    if item_type in {
        "directory",
        "folder",
        "collection",
    }:
        return "directory"

    if item.get("is_folder") is False:
        return "file"

    if item.get("is_dir") is False:
        return "file"

    if item.get("is_directory") is False:
        return "file"

    if item_type in {
        "file",
        "document",
    }:
        return "file"

    return "unknown"


def build_folder_upload_plan(
    items: Iterable[Any],
    *,
    destination_path: str,
    gateway: Any | None = None,
    declared_directories: Iterable[str] = (),
    limits: FolderUploadLimits | None = None,
) -> FolderUploadPlan:
    """
    Valida el manifiesto completo antes de tocar almacenamiento.

    ``declared_directories`` permite representar carpetas vacías en una
    futura implementación basada en manifiesto explícito.
    """

    limits = limits or FolderUploadLimits()

    destination = normalize_destination_path(
        destination_path,
        limits=limits,
    )

    raw_items = [
        _coerce_input(item)
        for item in items
    ]

    raw_directories = [
        str(path or "")
        for path in declared_directories
    ]

    if not raw_items and not raw_directories:
        raise FolderUploadValidationError(
            "empty_manifest",
            "La carpeta seleccionada no contiene elementos representables.",
        )

    if len(raw_items) > limits.max_files:
        raise FolderUploadValidationError(
            "file_count_exceeded",
            "El manifiesto supera el número máximo de archivos.",
        )

    if len(raw_directories) > limits.max_directories:
        raise FolderUploadValidationError(
            "directory_count_exceeded",
            "El manifiesto supera el número máximo de carpetas.",
        )

    normalized_directory_relpaths: set[str] = set()
    roots: set[str] = set()

    for raw_directory in raw_directories:
        normalized = normalize_relative_path(
            raw_directory,
            limits=limits,
            require_child=False,
        )

        normalized_directory_relpaths.add(normalized)
        roots.add(normalized.split("/", 1)[0])

    planned_files: list[PlannedFolderFile] = []
    file_relpaths: set[str] = set()
    total_size = 0

    for raw_item in raw_items:
        normalized = normalize_relative_path(
            raw_item.relative_path,
            limits=limits,
        )

        if normalized in file_relpaths:
            _reject(
                "duplicate_manifest_path",
                "El manifiesto contiene la misma ruta más de una vez.",
                path=normalized,
            )

        size = _uploaded_size(
            raw_item.uploaded_file,
            normalized,
        )

        if size > limits.max_file_size:
            _reject(
                "file_size_exceeded",
                "El archivo supera el tamaño individual permitido.",
                path=normalized,
            )

        total_size += size

        if total_size > limits.max_total_size:
            raise FolderUploadValidationError(
                "total_size_exceeded",
                "La carpeta supera el tamaño total permitido.",
            )

        relative_parent, filename = _parent_and_name(
            normalized
        )

        parts = normalized.split("/")
        roots.add(parts[0])
        file_relpaths.add(normalized)

        current_parts = parts[:-1]

        for index in range(1, len(current_parts) + 1):
            normalized_directory_relpaths.add(
                "/".join(current_parts[:index])
            )

        target_path = _join_path(
            destination,
            normalized,
        )

        target_parent, _ = _parent_and_name(target_path)

        planned_files.append(
            PlannedFolderFile(
                uploaded_file=raw_item.uploaded_file,
                relative_path=normalized,
                target_path=target_path,
                parent_path=target_parent,
                filename=filename,
                size=size,
            )
        )

    if len(roots) != 1:
        raise FolderUploadValidationError(
            "multiple_roots",
            "Todos los elementos deben pertenecer a una única carpeta raíz.",
        )

    root_name = next(iter(roots))

    for file_path in file_relpaths:
        if file_path in normalized_directory_relpaths:
            _reject(
                "file_directory_collision",
                "Una misma ruta está declarada como archivo y carpeta.",
                path=file_path,
            )

    directories = tuple(sorted(
        {
            _join_path(destination, relative)
            for relative in normalized_directory_relpaths
        },
        key=lambda path: (
            path.count("/"),
            path.casefold(),
        ),
    ))

    conflicts: list[FolderUploadConflict] = []

    if gateway is not None:
        for directory in directories:
            if gateway.path_exists(directory):
                conflicts.append(
                    FolderUploadConflict(
                        path=directory,
                        kind=_gateway_item_kind(
                            gateway,
                            directory,
                        ),
                    )
                )

        for planned in planned_files:
            if gateway.path_exists(planned.target_path):
                conflicts.append(
                    FolderUploadConflict(
                        path=planned.target_path,
                        kind=_gateway_item_kind(
                            gateway,
                            planned.target_path,
                        ),
                    )
                )

    return FolderUploadPlan(
        destination_path=destination,
        root_name=root_name,
        directories=directories,
        files=tuple(planned_files),
        total_size=total_size,
        conflicts=tuple(conflicts),
        limits=limits,
    )


@contextmanager
def _temporary_upload_name(
    uploaded_file: Any,
    filename: str,
):
    original_name = getattr(uploaded_file, "name", None)

    try:
        uploaded_file.name = filename
        yield uploaded_file
    finally:
        if original_name is not None:
            uploaded_file.name = original_name


def _auto_rename_target(
    gateway: Any,
    target_path: str,
    *,
    reserved_paths: set[str],
    max_attempts: int = 1000,
) -> str:
    parent, filename = _parent_and_name(target_path)
    parsed = PurePosixPath(filename)

    suffix = parsed.suffix
    stem = filename[:-len(suffix)] if suffix else filename

    for number in range(1, max_attempts + 1):
        candidate_name = f"{stem} ({number}){suffix}"
        candidate = _join_path(parent, candidate_name)

        if candidate in reserved_paths:
            continue

        if not gateway.path_exists(candidate):
            return candidate

    raise FolderUploadError(
        "rename_exhausted",
        "No se encontró un nombre alternativo disponible.",
        path=target_path,
    )


def _replace_existing_file(
    gateway: Any,
    planned: PlannedFolderFile,
) -> tuple[Mapping[str, Any], str]:
    """
    Reemplazo controlado:

    1. Sube primero un archivo temporal.
    2. Elimina el destino existente.
    3. Mueve el temporal al nombre definitivo.

    Si falla antes de eliminar el original, limpia el temporal.
    Si falla después de eliminarlo, conserva el temporal para recuperación.
    """

    temporary_name = (
        f".intasa-folder-upload-{uuid.uuid4().hex}.tmp"
    )
    temporary_path = _join_path(
        planned.parent_path,
        temporary_name,
    )

    with _temporary_upload_name(
        planned.uploaded_file,
        temporary_name,
    ):
        uploaded_item = gateway.upload_file(
            planned.parent_path,
            planned.uploaded_file,
        )

    try:
        gateway.delete_path(planned.target_path)
    except Exception:
        try:
            gateway.delete_path(temporary_path)
        except Exception:
            pass
        raise

    try:
        gateway.move_path(
            temporary_path,
            planned.target_path,
        )
    except Exception as exc:
        raise FolderUploadError(
            "replace_move_failed",
            (
                "El original fue retirado, pero no pudo completarse "
                f"el movimiento final. Temporal recuperable: {temporary_path}. "
                f"Detalle: {exc}"
            ),
            path=planned.target_path,
        ) from exc

    item = dict(uploaded_item or {})
    item["storage_key"] = planned.target_path
    item["name"] = planned.filename

    return item, planned.target_path


def execute_folder_upload(
    plan: FolderUploadPlan,
    *,
    gateway: Any,
    policy: str = POLICY_SKIP,
    allow_replace: bool = False,
    reference_writer: Callable[
        [PlannedFolderFile, Mapping[str, Any], str],
        Any,
    ] | None = None,
    progress_callback: Callable[[dict[str, Any]], Any] | None = None,
) -> FolderUploadExecutionResult:
    """
    Ejecuta un plan ya validado.

    No usa transacción global porque Nextcloud es un sistema externo.
    Cada archivo produce un resultado independiente.
    """

    if policy not in SUPPORTED_POLICIES:
        raise FolderUploadValidationError(
            "invalid_policy",
            "La política de colisiones no es válida.",
        )

    if policy == POLICY_REPLACE and not allow_replace:
        raise FolderUploadValidationError(
            "replace_not_authorized",
            "La política reemplazar requiere autorización explícita.",
        )

    result = FolderUploadExecutionResult(
        policy=policy,
        root_name=plan.root_name,
        total_files=plan.files_count,
        total_size=plan.total_size,
    )

    if policy == POLICY_CANCEL:
        existing_files = [
            planned.target_path
            for planned in plan.files
            if gateway.path_exists(planned.target_path)
        ]

        if existing_files:
            result.cancelled = True

            for planned in plan.files:
                result.file_results.append(
                    FolderUploadFileResult(
                        relative_path=planned.relative_path,
                        target_path=planned.target_path,
                        status="cancelled",
                        size=planned.size,
                        error_code="collision_cancelled",
                        error=(
                            "La operación fue cancelada porque existen "
                            "archivos con el mismo nombre."
                        ),
                    )
                )

            return result

    failed_directories: dict[str, str] = {}

    for directory in plan.directories:
        parent, name = _parent_and_name(directory)

        try:
            if gateway.path_exists(directory):
                kind = _gateway_item_kind(
                    gateway,
                    directory,
                )

                if kind == "file":
                    raise FolderUploadError(
                        "directory_blocked_by_file",
                        "La carpeta necesaria está ocupada por un archivo.",
                        path=directory,
                    )

                result.reused_folders.append(directory)
                continue

            gateway.create_directory(parent, name)
            result.created_folders.append(directory)

        except Exception as exc:
            failed_directories[directory] = str(exc)

    reserved_paths: set[str] = set()

    for index, planned in enumerate(plan.files, start=1):
        blocking_directory = next(
            (
                directory
                for directory in failed_directories
                if (
                    planned.parent_path == directory
                    or planned.parent_path.startswith(
                        directory + "/"
                    )
                )
            ),
            None,
        )

        if blocking_directory:
            result.file_results.append(
                FolderUploadFileResult(
                    relative_path=planned.relative_path,
                    target_path=planned.target_path,
                    status="error",
                    size=planned.size,
                    error_code="parent_directory_failed",
                    error=failed_directories[
                        blocking_directory
                    ],
                )
            )
            continue

        final_target = planned.target_path
        status = "uploaded"
        gateway_item: Mapping[str, Any] = {}
        reference_error = ""

        try:
            exists = gateway.path_exists(final_target)

            if exists and policy == POLICY_SKIP:
                # P2B2_RECONCILE_SKIPPED_REFERENCE
                reference_error = ""

                if reference_writer is not None:
                    try:
                        eventual_getter = getattr(
                            gateway,
                            "get_item_eventually",
                            None,
                        )

                        if callable(eventual_getter):
                            gateway_item = eventual_getter(
                                final_target
                            )
                        else:
                            gateway_item = gateway.get_item(
                                final_target
                            )

                        reference_writer(
                            planned,
                            gateway_item,
                            final_target,
                        )

                    except Exception as exc:
                        reference_error = str(exc)

                result.file_results.append(
                    FolderUploadFileResult(
                        relative_path=planned.relative_path,
                        target_path=final_target,
                        status="skipped",
                        size=planned.size,
                        error_code="existing_file",
                        error="El archivo ya existe.",
                        reference_error=reference_error,
                    )
                )
                continue

            if exists and policy == POLICY_CANCEL:
                result.cancelled = True

                result.file_results.append(
                    FolderUploadFileResult(
                        relative_path=planned.relative_path,
                        target_path=final_target,
                        status="cancelled",
                        size=planned.size,
                        error_code="collision_cancelled",
                        error="La operación fue cancelada.",
                    )
                )
                break

            if exists and policy == POLICY_RENAME:
                final_target = _auto_rename_target(
                    gateway,
                    final_target,
                    reserved_paths=reserved_paths,
                )
                status = "renamed"

            if exists and policy == POLICY_REPLACE:
                gateway_item, final_target = (
                    _replace_existing_file(
                        gateway,
                        planned,
                    )
                )
                status = "replaced"

            else:
                final_parent, final_name = _parent_and_name(
                    final_target
                )

                with _temporary_upload_name(
                    planned.uploaded_file,
                    final_name,
                ):
                    gateway_item = gateway.upload_file(
                        final_parent,
                        planned.uploaded_file,
                    )

            reserved_paths.add(final_target)

            if reference_writer is not None:
                try:
                    reference_writer(
                        planned,
                        gateway_item,
                        final_target,
                    )
                except Exception as exc:
                    reference_error = str(exc)

            result.file_results.append(
                FolderUploadFileResult(
                    relative_path=planned.relative_path,
                    target_path=final_target,
                    status=status,
                    size=planned.size,
                    reference_error=reference_error,
                )
            )

        except FolderUploadError as exc:
            result.file_results.append(
                FolderUploadFileResult(
                    relative_path=planned.relative_path,
                    target_path=final_target,
                    status="error",
                    size=planned.size,
                    error_code=exc.code,
                    error=exc.message,
                )
            )

        except Exception as exc:
            result.file_results.append(
                FolderUploadFileResult(
                    relative_path=planned.relative_path,
                    target_path=final_target,
                    status="error",
                    size=planned.size,
                    error_code="upload_failed",
                    error=str(exc),
                )
            )

        finally:
            if progress_callback is not None:
                progress_callback({
                    "completed": result.processed_files,
                    "total": result.total_files,
                    "pending": max(
                        result.total_files
                        - result.processed_files,
                        0,
                    ),
                    "percent": (
                        round(
                            result.processed_files
                            * 100
                            / result.total_files,
                            2,
                        )
                        if result.total_files
                        else 100
                    ),
                    "current_index": index,
                })

    return result
