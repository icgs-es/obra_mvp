from __future__ import annotations

import time

from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import requests

from .storage_providers import get_storage_provider
from .storage_providers.base import StorageProviderError


DAV_NS = "DAV:"
OC_NS = "http://owncloud.org/ns"


class CloudGatewayError(StorageProviderError):
    """Error controlado del explorador documental remoto."""


class NextcloudCloudGateway:
    """
    Navegación directa sobre el árbol documental de intasa-bridge.

    Nextcloud es la fuente de verdad. Django mantiene únicamente
    referencias de los archivos que se abren desde INTASA.
    """

    def __init__(self):
        self.provider = get_storage_provider("nextcloud")
        self.config = self.provider._config()

    @staticmethod
    def normalize_path(value: str, *, allow_empty: bool = True) -> str:
        raw = str(value or "").replace("\\", "/")

        parts = []

        for part in raw.split("/"):
            if part in ("", "."):
                continue

            if part == ".." or "\x00" in part:
                raise CloudGatewayError(
                    "La ruta documental no es válida."
                )

            parts.append(part)

        normalized = "/".join(parts)

        if not normalized and not allow_empty:
            raise CloudGatewayError(
                "La ruta documental está vacía."
            )

        return normalized

    def _dav_url(self, relative_path: str = "") -> str:
        base_url = str(self.config["base_url"]).rstrip("/")
        username = quote(
            str(self.config["username"]),
            safe="",
        )

        root = self.normalize_path(
            str(self.config.get("root") or ""),
            allow_empty=True,
        )

        relative = self.normalize_path(
            relative_path,
            allow_empty=True,
        )

        combined = "/".join(
            value
            for value in (root, relative)
            if value
        )

        encoded = "/".join(
            quote(part, safe="")
            for part in combined.split("/")
        )

        return (
            f"{base_url}/remote.php/dav/files/"
            f"{username}/{encoded}"
        )

    def _request(
        self,
        method: str,
        relative_path: str,
        **kwargs,
    ) -> requests.Response:
        try:
            return requests.request(
                method,
                self._dav_url(relative_path),
                auth=(
                    str(self.config["username"]),
                    str(self.config["app_password"]),
                ),
                timeout=int(
                    self.config.get("timeout") or 90
                ),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise CloudGatewayError(
                "No se pudo acceder al almacenamiento documental."
            ) from exc

    @staticmethod
    def _successful_prop(response_node):
        for propstat in response_node.findall(
            f"{{{DAV_NS}}}propstat"
        ):
            status = (
                propstat.findtext(
                    f"{{{DAV_NS}}}status"
                )
                or ""
            )

            if " 200 " in status:
                return propstat.find(
                    f"{{{DAV_NS}}}prop"
                )

        return response_node.find(
            f".//{{{DAV_NS}}}prop"
        )

    def _parse_item(
        self,
        response_node,
        *,
        storage_key: str,
    ) -> dict | None:
        prop = self._successful_prop(
            response_node
        )

        if prop is None:
            return None

        href = (
            response_node.findtext(
                f"{{{DAV_NS}}}href"
            )
            or ""
        )

        resource_type = prop.find(
            f"{{{DAV_NS}}}resourcetype"
        )

        is_folder = (
            resource_type is not None
            and resource_type.find(
                f"{{{DAV_NS}}}collection"
            )
            is not None
        )

        name = (
            prop.findtext(
                f"{{{DAV_NS}}}displayname"
            )
            or unquote(
                urlparse(href).path
            ).rstrip("/").split("/")[-1]
        )

        size_value = prop.findtext(
            f"{{{DAV_NS}}}getcontentlength"
        )

        try:
            size = int(size_value or 0)
        except (TypeError, ValueError):
            size = 0

        return {
            "name": name,
            "storage_key": storage_key,
            "is_folder": is_folder,
            "size": size,
            "content_type": (
                prop.findtext(
                    f"{{{DAV_NS}}}getcontenttype"
                )
                or ""
            ),
            "etag": (
                prop.findtext(
                    f"{{{DAV_NS}}}getetag"
                )
                or ""
            ).strip('"'),
            "file_id": (
                prop.findtext(
                    f"{{{OC_NS}}}fileid"
                )
                or ""
            ),
            "permissions": (
                prop.findtext(
                    f"{{{OC_NS}}}permissions"
                )
                or ""
            ),
            "modified": (
                prop.findtext(
                    f"{{{DAV_NS}}}getlastmodified"
                )
                or ""
            ),
            "href": href,
        }

    @staticmethod
    def _propfind_body() -> bytes:
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<d:propfind
    xmlns:d="DAV:"
    xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <d:getcontentlength/>
    <d:getcontenttype/>
    <d:getetag/>
    <d:getlastmodified/>
    <oc:fileid/>
    <oc:permissions/>
  </d:prop>
</d:propfind>
"""

    def list_directory(
        self,
        relative_path: str = "",
    ) -> list[dict]:
        directory_path = self.normalize_path(
            relative_path,
            allow_empty=True,
        )

        response = self._request(
            "PROPFIND",
            directory_path,
            headers={
                "Depth": "1",
                "Content-Type": (
                    "application/xml; charset=utf-8"
                ),
            },
            data=self._propfind_body(),
        )

        try:
            if response.status_code == 404:
                raise FileNotFoundError(
                    directory_path
                )

            if response.status_code != 207:
                raise CloudGatewayError(
                    "El almacenamiento devolvió "
                    f"HTTP {response.status_code}."
                )

            xml_root = ElementTree.fromstring(
                response.content
            )

            request_path = unquote(
                urlparse(
                    self._dav_url(directory_path)
                ).path
            ).rstrip("/")

            items = []

            for response_node in xml_root.findall(
                f"{{{DAV_NS}}}response"
            ):
                href = (
                    response_node.findtext(
                        f"{{{DAV_NS}}}href"
                    )
                    or ""
                )

                node_path = unquote(
                    urlparse(href).path
                ).rstrip("/")

                if node_path == request_path:
                    continue

                prop = self._successful_prop(
                    response_node
                )

                if prop is None:
                    continue

                name = (
                    prop.findtext(
                        f"{{{DAV_NS}}}displayname"
                    )
                    or node_path.split("/")[-1]
                )

                storage_key = "/".join(
                    value
                    for value in (
                        directory_path,
                        name,
                    )
                    if value
                )

                item = self._parse_item(
                    response_node,
                    storage_key=storage_key,
                )

                if item:
                    items.append(item)

            items.sort(
                key=lambda item: (
                    not item["is_folder"],
                    item["name"].casefold(),
                )
            )

            return items

        except ElementTree.ParseError as exc:
            raise CloudGatewayError(
                "La respuesta documental no es válida."
            ) from exc

        finally:
            response.close()

    def get_item(
        self,
        relative_path: str,
    ) -> dict:
        storage_key = self.normalize_path(
            relative_path,
            allow_empty=False,
        )

        response = self._request(
            "PROPFIND",
            storage_key,
            headers={
                "Depth": "0",
                "Content-Type": (
                    "application/xml; charset=utf-8"
                ),
            },
            data=self._propfind_body(),
        )

        try:
            if response.status_code == 404:
                raise FileNotFoundError(
                    storage_key
                )

            if response.status_code != 207:
                raise CloudGatewayError(
                    "El almacenamiento devolvió "
                    f"HTTP {response.status_code}."
                )

            xml_root = ElementTree.fromstring(
                response.content
            )

            response_node = xml_root.find(
                f"{{{DAV_NS}}}response"
            )

            if response_node is None:
                raise FileNotFoundError(
                    storage_key
                )

            item = self._parse_item(
                response_node,
                storage_key=storage_key,
            )

            if item is None:
                raise FileNotFoundError(
                    storage_key
                )

            return item

        except ElementTree.ParseError as exc:
            raise CloudGatewayError(
                "La respuesta documental no es válida."
            ) from exc

        finally:
            response.close()

    @staticmethod
    def normalize_name(value: str) -> str:
        name = str(value or "").strip()

        if (
            not name
            or name in (".", "..")
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or any(ord(char) < 32 for char in name)
        ):
            raise CloudGatewayError(
                "El nombre documental no es válido."
            )

        return name

    def path_exists(
        self,
        relative_path: str,
    ) -> bool:
        storage_key = self.normalize_path(
            relative_path,
            allow_empty=False,
        )

        response = self._request(
            "PROPFIND",
            storage_key,
            headers={
                "Depth": "0",
                "Content-Type": (
                    "application/xml; charset=utf-8"
                ),
            },
            data=self._propfind_body(),
        )

        try:
            if response.status_code == 404:
                return False

            if response.status_code == 207:
                return True

            raise CloudGatewayError(
                "El almacenamiento devolvió "
                f"HTTP {response.status_code}."
            )

        finally:
            response.close()

    def create_directory(
        self,
        parent_path: str,
        name: str,
    ) -> dict:
        parent = self.normalize_path(
            parent_path,
            allow_empty=True,
        )

        clean_name = self.normalize_name(name)

        target = "/".join(
            value
            for value in (
                parent,
                clean_name,
            )
            if value
        )

        if self.path_exists(target):
            raise CloudGatewayError(
                "Ya existe un elemento con ese nombre."
            )

        response = self._request(
            "MKCOL",
            target,
        )

        try:
            if response.status_code != 201:
                raise CloudGatewayError(
                    "No se pudo crear la carpeta. "
                    f"HTTP {response.status_code}."
                )
        finally:
            response.close()

        return self.get_item(target)

    # P2B2_EVENTUAL_ITEM_READ
    def get_item_eventually(
        self,
        relative_path: str,
        *,
        attempts: int = 6,
        initial_delay: float = 0.15,
    ) -> dict:
        """
        Recupera metadatos después de una escritura DAV.

        Nextcloud puede aceptar el PUT antes de que una
        consulta PROPFIND inmediata vea el nuevo file_id.
        Este reintento es breve y nunca repite el PUT.
        """
        attempts = max(
            int(attempts),
            1,
        )

        initial_delay = max(
            float(initial_delay),
            0.0,
        )

        for attempt in range(attempts):
            try:
                return self.get_item(
                    relative_path
                )

            except CloudGatewayError:
                if attempt + 1 >= attempts:
                    raise

                delay = min(
                    initial_delay
                    * (2 ** attempt),
                    1.0,
                )

                if delay:
                    time.sleep(delay)


    def upload_file(
        self,
        parent_path: str,
        uploaded_file,
    ) -> dict:
        parent = self.normalize_path(
            parent_path,
            allow_empty=True,
        )

        original_name = str(
            getattr(uploaded_file, "name", "")
            or ""
        ).replace("\\", "/")

        clean_name = self.normalize_name(
            original_name.split("/")[-1]
        )

        target = "/".join(
            value
            for value in (
                parent,
                clean_name,
            )
            if value
        )

        if self.path_exists(target):
            raise CloudGatewayError(
                f"Ya existe el archivo «{clean_name}»."
            )

        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass

        content_type = str(
            getattr(
                uploaded_file,
                "content_type",
                "",
            )
            or "application/octet-stream"
        )

        headers = {
            "Content-Type": content_type,
        }

        size = getattr(
            uploaded_file,
            "size",
            None,
        )

        if size is not None:
            headers["Content-Length"] = str(
                int(size)
            )

        response = self._request(
            "PUT",
            target,
            headers=headers,
            data=uploaded_file,
        )

        try:
            if response.status_code not in (
                201,
                204,
            ):
                raise CloudGatewayError(
                    "No se pudo subir el archivo "
                    f"«{clean_name}». "
                    f"HTTP {response.status_code}."
                )
        finally:
            response.close()

        return self.get_item_eventually(
            target
        )

    def delete_path(
        self,
        relative_path: str,
    ) -> None:
        storage_key = self.normalize_path(
            relative_path,
            allow_empty=False,
        )

        response = self._request(
            "DELETE",
            storage_key,
        )

        try:
            if response.status_code not in (
                204,
                404,
            ):
                raise CloudGatewayError(
                    "No se pudo eliminar el elemento. "
                    f"HTTP {response.status_code}."
                )
        finally:
            response.close()

    def move_path(
        self,
        source_path: str,
        destination_path: str,
    ) -> dict:
        source = self.normalize_path(
            source_path,
            allow_empty=False,
        )

        destination = self.normalize_path(
            destination_path,
            allow_empty=False,
        )

        if source == destination:
            raise CloudGatewayError(
                "El origen y el destino son iguales."
            )

        if destination.startswith(source + "/"):
            raise CloudGatewayError(
                "No se puede mover una carpeta "
                "dentro de sí misma."
            )

        if not self.path_exists(source):
            raise FileNotFoundError(source)

        if self.path_exists(destination):
            raise CloudGatewayError(
                "Ya existe un elemento en el destino."
            )

        response = self._request(
            "MOVE",
            source,
            headers={
                "Destination": self._dav_url(
                    destination
                ),
                "Overwrite": "F",
            },
            allow_redirects=False,
        )

        try:
            if response.status_code not in (
                201,
                204,
            ):
                raise CloudGatewayError(
                    "No se pudo mover el elemento. "
                    f"HTTP {response.status_code}."
                )
        finally:
            response.close()

        return self.get_item(destination)

