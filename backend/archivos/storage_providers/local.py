from __future__ import annotations

from typing import Any, BinaryIO

from .base import StorageProvider, StorageProviderError


class LocalStorageProvider(StorageProvider):
    """Proveedor basado en el FileField y storage configurado en Django."""

    code = "local"
    public_label = "LOCAL"

    @staticmethod
    def _file_field(archivo: Any):
        fichero = getattr(archivo, "fichero", None)

        if not fichero or not getattr(fichero, "name", ""):
            raise StorageProviderError("El archivo no tiene fichero asociado.")

        return fichero

    def open(self, archivo: Any, mode: str = "rb") -> BinaryIO:
        return self._file_field(archivo).open(mode)

    def exists(self, archivo: Any) -> bool:
        fichero = self._file_field(archivo)
        return fichero.storage.exists(fichero.name)

    def size(self, archivo: Any) -> int:
        fichero = self._file_field(archivo)
        return int(fichero.storage.size(fichero.name))

    def delete(self, archivo: Any) -> None:
        fichero = self._file_field(archivo)
        fichero.storage.delete(fichero.name)

    def url(self, archivo: Any) -> str:
        return self._file_field(archivo).url
