from __future__ import annotations

from typing import Dict

from .base import StorageProvider, StorageProviderError
from .local import LocalStorageProvider
from .nextcloud import NextcloudStorageProvider


_PROVIDERS: Dict[str, StorageProvider] = {
    LocalStorageProvider.code: LocalStorageProvider(),
    NextcloudStorageProvider.code: NextcloudStorageProvider(),
}


def register_storage_provider(provider: StorageProvider) -> None:
    code = str(provider.code or "").strip().lower()

    if not code:
        raise StorageProviderError("El proveedor no tiene código.")

    _PROVIDERS[code] = provider


def get_storage_provider(code: str | None = None) -> StorageProvider:
    normalized = str(code or "local").strip().lower()

    try:
        return _PROVIDERS[normalized]
    except KeyError as exc:
        raise StorageProviderError(
            f"Proveedor documental no registrado: {normalized}"
        ) from exc


def registered_storage_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))
