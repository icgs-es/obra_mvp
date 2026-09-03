from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, BinaryIO


class StorageProviderError(RuntimeError):
    """Error controlado producido por un proveedor documental."""


class StorageProvider(ABC):
    """
    Contrato común para los motores documentales de INTASA Documents.

    Los proveedores trabajan actualmente con una instancia Archivo.
    Posteriormente podrán utilizar referencias remotas sin cambiar las vistas.
    """

    code = "base"

    @abstractmethod
    def open(self, archivo: Any, mode: str = "rb") -> BinaryIO:
        raise NotImplementedError

    @abstractmethod
    def exists(self, archivo: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    def size(self, archivo: Any) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete(self, archivo: Any) -> None:
        raise NotImplementedError

    def supports_online_edit(self, archivo: Any) -> bool:
        """
        Indica si el proveedor puede crear una sesión de edición
        online para el documento indicado.
        """
        return False

    def create_online_edit_session(self, archivo: Any) -> dict:
        """
        Devuelve los datos efímeros necesarios para iniciar el
        editor online.

        Los providers sin esta capacidad deben mantener el
        comportamiento seguro por defecto.
        """
        raise StorageProviderError(
            "Este proveedor no admite edición online."
        )

    @abstractmethod
    def url(self, archivo: Any) -> str:
        raise NotImplementedError
