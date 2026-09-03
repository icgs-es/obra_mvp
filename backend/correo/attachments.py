import os
import re
from dataclasses import dataclass
from email import message_from_bytes
from email.policy import default

from .models import CuentaCorreo
from .reader import (
    CorreoReaderError,
    MensajeNoEncontrado,
    _decode_header_value,
    _first_fetch_tuple,
    _open_imap,
    obtener_mensaje,
)


MAX_ATTACHMENT_BYTES = (
    15 * 1024 * 1024
)


@dataclass(frozen=True)
class AdjuntoContenido:
    indice: int
    nombre: str
    tipo_contenido: str
    tamano_bytes: int
    contenido: bytes


def nombre_adjunto_seguro(
    value: str,
) -> str:
    value = str(
        value or ""
    ).replace(
        "\\",
        "/",
    )

    filename = os.path.basename(
        value
    )

    filename = re.sub(
        r"[\x00-\x1f\x7f]",
        "_",
        filename,
    )

    filename = filename.strip()

    while filename.startswith("."):
        filename = filename[1:]

    if not filename:
        filename = "adjunto.bin"

    return filename[:240]


def _es_adjunto(part) -> bool:
    filename = _decode_header_value(
        part.get_filename()
    )

    disposition = (
        part.get_content_disposition()
    )

    return bool(
        disposition == "attachment"
        or filename
    )


def obtener_adjunto(
    cuenta: CuentaCorreo,
    uid: int | str,
    indice: int | str,
    timeout: int = 20,
) -> AdjuntoContenido:
    """
    Recupera un único adjunto mediante un índice MIME estable.

    El mensaje se consulta con BODY.PEEK para no cambiar
    accidentalmente el estado leído/no leído.
    """
    try:
        indice_number = int(
            indice
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MensajeNoEncontrado(
            "El identificador del adjunto no es válido."
        ) from exc

    if indice_number < 0:
        raise MensajeNoEncontrado(
            "El identificador del adjunto no es válido."
        )

    # Esta lectura previa aplica los límites y validaciones
    # existentes del lector de correo.
    detalle = obtener_mensaje(
        cuenta,
        uid,
        timeout=timeout,
    )

    if indice_number >= len(
        detalle.adjuntos
    ):
        raise MensajeNoEncontrado(
            "El adjunto ya no está disponible."
        )

    imap = None
    password = ""

    try:
        imap, password = _open_imap(
            cuenta,
            timeout,
        )

        status, _ = imap.select(
            "INBOX",
            readonly=True,
        )

        if status != "OK":
            raise CorreoReaderError(
                "IONOS no permitió abrir la bandeja."
            )

        status, message_data = imap.uid(
            "fetch",
            str(int(uid)),
            "(BODY.PEEK[])",
        )

        message_tuple = _first_fetch_tuple(
            message_data
        )

        if (
            status != "OK"
            or message_tuple is None
        ):
            raise MensajeNoEncontrado(
                "El mensaje ya no está disponible."
            )

        raw_message = message_tuple[1]

        if not isinstance(
            raw_message,
            bytes,
        ):
            raise CorreoReaderError(
                "El contenido del mensaje no es válido."
            )

        message = message_from_bytes(
            raw_message,
            policy=default,
        )

        attachment_index = -1

        for part in message.walk():
            if part.is_multipart():
                continue

            if not _es_adjunto(part):
                continue

            attachment_index += 1

            if attachment_index != indice_number:
                continue

            payload = part.get_payload(
                decode=True
            )

            if payload is None:
                payload = b""

            if not isinstance(
                payload,
                bytes,
            ):
                raise CorreoReaderError(
                    "El adjunto no contiene datos válidos."
                )

            size = len(payload)

            if size > MAX_ATTACHMENT_BYTES:
                raise CorreoReaderError(
                    (
                        "El adjunto supera el límite "
                        "de seguridad de 15 MB."
                    )
                )

            filename = nombre_adjunto_seguro(
                _decode_header_value(
                    part.get_filename()
                )
            )

            return AdjuntoContenido(
                indice=indice_number,
                nombre=filename,
                tipo_contenido=(
                    part.get_content_type()
                    or "application/octet-stream"
                ),
                tamano_bytes=size,
                contenido=payload,
            )

        raise MensajeNoEncontrado(
            "El adjunto ya no está disponible."
        )

    except (
        MensajeNoEncontrado,
        CorreoReaderError,
    ):
        raise

    except Exception as exc:
        safe_text = str(exc)

        if password:
            safe_text = safe_text.replace(
                password,
                "[CREDENCIAL OCULTA]",
            )

        raise CorreoReaderError(
            (
                "No se pudo recuperar el adjunto. "
                f"{type(exc).__name__}: {safe_text}"
            )[:1200]
        ) from exc

    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass
