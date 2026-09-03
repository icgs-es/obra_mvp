from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

import requests

from .base import StorageProvider, StorageProviderError


DAV_NS = "DAV:"
OC_NS = "http://owncloud.org/ns"


class NextcloudStorageProvider(StorageProvider):
    """Motor documental Nextcloud mediante WebDAV."""

    code = "nextcloud"
    public_label = "INTASA CLOUD"

    def _config(self) -> dict:
        path = Path(
            os.environ.get(
                "INTASA_DOCUMENTS_NEXTCLOUD_CONFIG",
                "/app/infra/secrets/nextcloud_bridge.json",
            )
        )

        if not path.is_file():
            raise StorageProviderError(
                f"No existe la configuración documental: {path}"
            )

        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise StorageProviderError(
                "Configuración documental no válida."
            ) from exc

        required = ("base_url", "username", "app_password")

        missing = [
            key
            for key in required
            if not str(config.get(key) or "").strip()
        ]

        if missing:
            raise StorageProviderError(
                "Faltan parámetros: " + ", ".join(missing)
            )

        return config

    @staticmethod
    def _clean_path(value: str) -> str:
        parts = [
            part
            for part in str(value or "").replace("\\", "/").split("/")
            if part not in ("", ".", "..")
        ]

        if not parts:
            raise StorageProviderError("Ruta remota no válida.")

        return "/".join(parts)

    def _remote_path(self, archivo: Any) -> str:
        """
        Resuelve la clave opaca del objeto documental.

        storage_key es el contrato genérico de INTASA Documents.
        remote_path se conserva temporalmente como compatibilidad
        con los smoke tests realizados antes de H5B.2B.
        """
        storage_key = str(
            getattr(archivo, "storage_key", "") or ""
        ).strip()

        legacy_remote_path = str(
            getattr(archivo, "remote_path", "") or ""
        ).strip()

        return self._clean_path(
            storage_key or legacy_remote_path
        )

    def _dav_url(self, remote_path: str) -> str:
        config = self._config()

        base_url = str(config["base_url"]).rstrip("/")
        username = quote(str(config["username"]), safe="")
        root = str(config.get("root") or "").strip("/")

        combined = "/".join(
            value
            for value in (root, self._clean_path(remote_path))
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
        remote_path: str,
        **kwargs,
    ) -> requests.Response:
        config = self._config()

        try:
            return requests.request(
                method,
                self._dav_url(remote_path),
                auth=(
                    str(config["username"]),
                    str(config["app_password"]),
                ),
                timeout=int(config.get("timeout") or 90),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise StorageProviderError(
                f"Error conectando con el motor documental: {exc}"
            ) from exc

    def metadata(self, archivo: Any) -> dict:
        remote_path = self._remote_path(archivo)

        body = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <d:getcontentlength/>
    <d:getetag/>
    <d:getcontenttype/>
    <oc:fileid/>
  </d:prop>
</d:propfind>
"""

        response = self._request(
            "PROPFIND",
            remote_path,
            headers={
                "Depth": "0",
                "Content-Type": "application/xml; charset=utf-8",
            },
            data=body.encode("utf-8"),
        )

        try:
            if response.status_code == 404:
                raise FileNotFoundError(remote_path)

            if response.status_code != 207:
                raise StorageProviderError(
                    f"PROPFIND devolvió HTTP {response.status_code}"
                )

            root = ElementTree.fromstring(response.content)

            size = root.findtext(
                f".//{{{DAV_NS}}}getcontentlength"
            )
            etag = root.findtext(
                f".//{{{DAV_NS}}}getetag"
            ) or ""
            content_type = root.findtext(
                f".//{{{DAV_NS}}}getcontenttype"
            ) or ""
            file_id = root.findtext(
                f".//{{{OC_NS}}}fileid"
            ) or ""

            return {
                "size": int(size or 0),
                "etag": etag.strip('"'),
                "content_type": content_type,
                "file_id": file_id,
            }

        finally:
            response.close()

    def open(self, archivo: Any, mode: str = "rb") -> BinaryIO:
        if mode != "rb":
            raise StorageProviderError(
                f"Modo no soportado: {mode}"
            )

        remote_path = self._remote_path(archivo)
        response = self._request(
            "GET",
            remote_path,
            stream=True,
        )

        if response.status_code == 404:
            response.close()
            raise FileNotFoundError(remote_path)

        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise StorageProviderError(
                f"GET documental devolvió HTTP {status}"
            )

        temporary = SpooledTemporaryFile(
            max_size=16 * 1024 * 1024,
            mode="w+b",
        )

        try:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    temporary.write(chunk)

            temporary.seek(0)
            return temporary

        except Exception:
            temporary.close()
            raise

        finally:
            response.close()

    def exists(self, archivo: Any) -> bool:
        try:
            self.metadata(archivo)
            return True
        except FileNotFoundError:
            return False

    def size(self, archivo: Any) -> int:
        return int(self.metadata(archivo)["size"])

    def delete(self, archivo: Any) -> None:
        response = self._request(
            "DELETE",
            self._remote_path(archivo),
        )

        try:
            if response.status_code not in (204, 404):
                raise StorageProviderError(
                    f"DELETE devolvió HTTP {response.status_code}"
                )
        finally:
            response.close()

    def supports_online_edit(self, archivo: Any) -> bool:
        object_id = str(
            getattr(archivo, "storage_object_id", "") or ""
        ).strip()

        if not object_id.isdigit():
            return False

        mime_type = str(
            getattr(archivo, "mime_type", "") or ""
        ).lower()

        name = str(
            getattr(archivo, "nombre_original", "") or ""
        ).lower()

        supported_mime_types = {
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.ms-powerpoint",
            "application/vnd.oasis.opendocument.text",
            "application/vnd.oasis.opendocument.spreadsheet",
            "application/vnd.oasis.opendocument.presentation",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/csv",
            "text/plain",
        }

        supported_extensions = (
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
            ".csv",
            ".txt",
            ".rtf",
        )

        return (
            mime_type in supported_mime_types
            or name.endswith(supported_extensions)
        )

    def create_online_edit_session(self, archivo: Any) -> dict:
        if not self.supports_online_edit(archivo):
            raise StorageProviderError(
                "El documento no admite edición online."
            )

        config = self._config()

        external_app_token = str(
            config.get("external_app_token") or ""
        ).strip()

        if not external_app_token:
            raise StorageProviderError(
                "No está configurado el canal de edición online."
            )

        file_id = str(
            getattr(archivo, "storage_object_id", "") or ""
        ).strip()

        if not file_id.isdigit():
            raise StorageProviderError(
                "El documento no tiene identificador remoto válido."
            )

        endpoint = (
            str(config["base_url"]).rstrip("/")
            + "/index.php/apps/richdocuments/"
            + "ajax/extapp/data/"
            + quote(file_id, safe="")
        )

        try:
            response = requests.post(
                endpoint,
                auth=(
                    str(config["username"]),
                    str(config["app_password"]),
                ),
                data={
                    "secret_token": external_app_token,
                },
                headers={
                    "Accept": "application/json",
                },
                timeout=int(config.get("timeout") or 90),
            )
        except requests.RequestException as exc:
            raise StorageProviderError(
                "No se pudo iniciar la sesión de edición."
            ) from exc

        try:
            if response.status_code != 200:
                raise StorageProviderError(
                    "El motor Office devolvió "
                    f"HTTP {response.status_code}."
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise StorageProviderError(
                    "El motor Office devolvió una respuesta no válida."
                ) from exc

            if payload.get("status") != "success":
                raise StorageProviderError(
                    str(
                        payload.get("message")
                        or "No se pudo iniciar el editor."
                    )
                )

            urlsrc = str(
                payload.get("urlsrc") or ""
            ).strip()

            access_token = str(
                payload.get("token") or ""
            ).strip()

            instance_id = str(
                config.get("instance_id") or ""
            ).strip()

            callback_url = str(
                config.get("wopi_callback_url")
                or config.get("base_url")
                or ""
            ).rstrip("/")

            parsed_urlsrc = urlparse(urlsrc)
            parsed_callback = urlparse(callback_url)

            if (
                parsed_urlsrc.scheme != "https"
                or not parsed_urlsrc.netloc
                or parsed_callback.scheme != "https"
                or not parsed_callback.netloc
                or not access_token
                or not instance_id
                or not instance_id.isalnum()
            ):
                raise StorageProviderError(
                    "La sesión Office recibida no es válida."
                )

            wopi_file_id = (
                f"{file_id}_{instance_id}"
            )

            wopi_src = (
                callback_url
                + "/index.php/apps/richdocuments/"
                + "wopi/files/"
                + quote(wopi_file_id, safe="")
            )

            if urlsrc.endswith(("?", "&")):
                separator = ""
            elif "?" in urlsrc:
                separator = "&"
            else:
                separator = "?"

            action_url = (
                urlsrc
                + separator
                + "WOPISrc="
                + quote(wopi_src, safe="")
                + "&lang=es-ES"
                + "&closebutton=1"
                + "&revisionhistory=1"
            )

            parsed_action = urlparse(action_url)

            if (
                parsed_action.scheme != "https"
                or not parsed_action.netloc
                or "WOPISrc=" not in action_url
            ):
                raise StorageProviderError(
                    "No se pudo construir la URL WOPI."
                )

            return {
                "action_url": action_url,
                "wopi_src": wopi_src,
                "access_token": access_token,
                "access_token_ttl": 0,
                "provider": self.code,
                "object_id": file_id,
            }

        finally:
            response.close()

    def url(self, archivo: Any) -> str:
        return self._dav_url(self._remote_path(archivo))
