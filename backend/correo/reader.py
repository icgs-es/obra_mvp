import imaplib
import re
import ssl
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from django.utils import timezone

from .crypto import CorreoCryptoError
from .models import CuentaCorreo


MAX_MESSAGE_BYTES = 15 * 1024 * 1024
MAX_BODY_CHARS = 250_000


class CorreoReaderError(RuntimeError):
    """Error seguro relacionado con la lectura del correo."""


class MensajeNoEncontrado(CorreoReaderError):
    """El UID solicitado no existe dentro de la bandeja."""


@dataclass(frozen=True)
class AdjuntoResumen:
    nombre: str
    tipo_contenido: str
    tamano_bytes: int


@dataclass(frozen=True)
class MensajeDetalle:
    uid: str
    asunto: str
    remitente_nombre: str
    remitente_email: str
    destinatarios: str
    copia: str
    fecha: datetime | None
    fecha_original: str
    cuerpo_texto: str
    leido: bool
    tamano_bytes: int
    contenido_recortado: bool
    adjuntos: tuple[AdjuntoResumen, ...]


@dataclass(frozen=True)
class ResultadoEstadoLectura:
    uid: str
    leido: bool
    no_leidos: int


class _HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    }

    SKIP_TAGS = {
        "canvas",
        "noscript",
        "script",
        "style",
        "svg",
    }

    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if (
            self.skip_depth == 0
            and tag in self.BLOCK_TAGS
        ):
            self.parts.append("\n")

    def handle_endtag(
        self,
        tag,
    ):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return

        if (
            self.skip_depth == 0
            and tag in self.BLOCK_TAGS
        ):
            self.parts.append("\n")

    def handle_data(
        self,
        data,
    ):
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(
            self.parts
        )

        lines = [
            re.sub(
                r"[ \t]+",
                " ",
                line,
            ).strip()
            for line in raw.replace(
                "\r\n",
                "\n",
            ).replace(
                "\r",
                "\n",
            ).splitlines()
        ]

        cleaned = "\n".join(
            lines
        )

        cleaned = re.sub(
            r"\n{3,}",
            "\n\n",
            cleaned,
        )

        return cleaned.strip()


def html_to_safe_text(
    value: str,
) -> str:
    parser = _HTMLTextExtractor()

    try:
        parser.feed(
            value
        )
        parser.close()
    except Exception:
        return ""

    return parser.text()


def _safe_error(
    exc: Exception,
    password: str,
) -> str:
    text = str(exc)

    if password:
        text = text.replace(
            password,
            "[CREDENCIAL OCULTA]",
        )

    return (
        f"{type(exc).__name__}: {text}"
    )[:1000]


def _decode_header_value(
    raw_value,
) -> str:
    if not raw_value:
        return ""

    raw_text = str(
        raw_value
    )

    parts: list[str] = []

    for value, encoding in decode_header(
        raw_text
    ):
        if isinstance(
            value,
            bytes,
        ):
            selected_encoding = (
                encoding
                or "utf-8"
            )

            try:
                decoded = value.decode(
                    selected_encoding,
                    errors="replace",
                )
            except LookupError:
                decoded = value.decode(
                    "utf-8",
                    errors="replace",
                )
        else:
            decoded = value

        parts.append(
            decoded
        )

    return "".join(
        parts
    ).strip()


def _parse_message_date(
    raw_date: str,
) -> datetime | None:
    if not raw_date:
        return None

    try:
        value = parsedate_to_datetime(
            raw_date
        )

        if value is None:
            return None

        if timezone.is_naive(
            value
        ):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return timezone.localtime(
            value
        )
    except Exception:
        return None


def _decode_text_part(
    part,
) -> str:
    payload = part.get_payload(
        decode=True
    )

    if payload is None:
        raw_payload = part.get_payload()

        if isinstance(
            raw_payload,
            str,
        ):
            return raw_payload

        return ""

    charset = (
        part.get_content_charset()
        or "utf-8"
    )

    try:
        return payload.decode(
            charset,
            errors="replace",
        )
    except LookupError:
        return payload.decode(
            "utf-8",
            errors="replace",
        )


def _extract_body_text(
    message,
) -> str:
    plain_candidates: list[str] = []
    html_candidates: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue

        filename = part.get_filename()
        disposition = (
            part.get_content_disposition()
        )

        if (
            disposition == "attachment"
            or filename
        ):
            continue

        content_type = (
            part.get_content_type()
        )

        if content_type not in (
            "text/plain",
            "text/html",
        ):
            continue

        decoded = _decode_text_part(
            part
        )

        if not decoded.strip():
            continue

        if content_type == "text/plain":
            plain_candidates.append(
                decoded
            )
        else:
            html_candidates.append(
                decoded
            )

    if plain_candidates:
        body = plain_candidates[0]
    elif html_candidates:
        body = html_to_safe_text(
            html_candidates[0]
        )
    else:
        body = (
            "El mensaje no contiene "
            "una parte de texto compatible."
        )

    body = body.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).strip()

    return body


def _extract_attachments(
    message,
) -> tuple[AdjuntoResumen, ...]:
    attachments: list[
        AdjuntoResumen
    ] = []

    for part in message.walk():
        if part.is_multipart():
            continue

        filename = _decode_header_value(
            part.get_filename()
        )

        disposition = (
            part.get_content_disposition()
        )

        if (
            disposition != "attachment"
            and not filename
        ):
            continue

        payload = part.get_payload(
            decode=True
        )

        size = (
            len(payload)
            if isinstance(
                payload,
                bytes,
            )
            else 0
        )

        attachments.append(
            AdjuntoResumen(
                nombre=(
                    filename
                    or "Adjunto sin nombre"
                ),
                tipo_contenido=(
                    part.get_content_type()
                    or "application/octet-stream"
                ),
                tamano_bytes=size,
            )
        )

    return tuple(
        attachments
    )


def _first_fetch_tuple(
    fetch_data,
):
    if not fetch_data:
        return None

    for item in fetch_data:
        if (
            isinstance(item, tuple)
            and len(item) >= 2
        ):
            return item

    return None


def _open_imap(
    cuenta: CuentaCorreo,
    timeout: int,
):
    password = cuenta.get_password()

    context = ssl.create_default_context()

    imap = imaplib.IMAP4_SSL(
        host=cuenta.imap_host,
        port=cuenta.imap_port,
        ssl_context=context,
        timeout=timeout,
    )

    try:
        imap.login(
            cuenta.direccion,
            password,
        )
    except Exception:
        try:
            imap.logout()
        except Exception:
            pass

        raise

    return imap, password


def obtener_mensaje(
    cuenta: CuentaCorreo,
    uid: int | str,
    timeout: int = 15,
) -> MensajeDetalle:
    if not cuenta.activa:
        raise CorreoReaderError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoReaderError(
            "La conexión con IONOS no está verificada."
        )

    try:
        uid_number = int(
            uid
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MensajeNoEncontrado(
            "El identificador del mensaje no es válido."
        ) from exc

    if uid_number <= 0:
        raise MensajeNoEncontrado(
            "El identificador del mensaje no es válido."
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

        status, metadata_data = imap.uid(
            "fetch",
            str(uid_number),
            (
                "(RFC822.SIZE FLAGS "
                "BODY.PEEK[HEADER.FIELDS "
                "(SUBJECT FROM TO CC DATE MESSAGE-ID)])"
            ),
        )

        metadata_tuple = _first_fetch_tuple(
            metadata_data
        )

        if (
            status != "OK"
            or metadata_tuple is None
        ):
            raise MensajeNoEncontrado(
                "El mensaje ya no está disponible."
            )

        metadata = metadata_tuple[0]

        if not isinstance(
            metadata,
            bytes,
        ):
            raise MensajeNoEncontrado(
                "IONOS no devolvió metadatos válidos."
            )

        size_match = re.search(
            rb"\bRFC822\.SIZE\s+(\d+)\b",
            metadata,
        )

        size = (
            int(size_match.group(1))
            if size_match
            else 0
        )

        flags_match = re.search(
            rb"\bFLAGS\s+\(([^)]*)\)",
            metadata,
        )

        flags = (
            flags_match.group(1)
            if flags_match
            else b""
        )

        leido = (
            b"\\Seen" in flags
        )

        raw_headers = metadata_tuple[1]

        if not isinstance(
            raw_headers,
            bytes,
        ):
            raw_headers = b""

        header_message = message_from_bytes(
            raw_headers,
            policy=default,
        )

        asunto = _decode_header_value(
            header_message.get(
                "Subject"
            )
        ) or "(Sin asunto)"

        remitente_raw = _decode_header_value(
            header_message.get(
                "From"
            )
        )

        (
            remitente_nombre,
            remitente_email,
        ) = parseaddr(
            remitente_raw
        )

        remitente_nombre = (
            remitente_nombre.strip()
            or remitente_email
            or "Remitente desconocido"
        )

        destinatarios = _decode_header_value(
            header_message.get(
                "To"
            )
        )

        copia = _decode_header_value(
            header_message.get(
                "Cc"
            )
        )

        raw_date = _decode_header_value(
            header_message.get(
                "Date"
            )
        )

        fecha = _parse_message_date(
            raw_date
        )

        if (
            size
            and size > MAX_MESSAGE_BYTES
        ):
            return MensajeDetalle(
                uid=str(uid_number),
                asunto=asunto,
                remitente_nombre=remitente_nombre,
                remitente_email=remitente_email,
                destinatarios=destinatarios,
                copia=copia,
                fecha=fecha,
                fecha_original=raw_date,
                cuerpo_texto=(
                    "Este mensaje supera el límite "
                    "de lectura segura de 15 MB. "
                    "En una versión posterior podrá "
                    "abrirse o descargarse bajo demanda."
                ),
                leido=leido,
                tamano_bytes=size,
                contenido_recortado=True,
                adjuntos=(),
            )

        status, message_data = imap.uid(
            "fetch",
            str(uid_number),
            "(BODY.PEEK[])",
        )

        message_tuple = _first_fetch_tuple(
            message_data
        )

        if (
            status != "OK"
            or message_tuple is None
        ):
            raise CorreoReaderError(
                "IONOS no devolvió el contenido del mensaje."
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

        body = _extract_body_text(
            message
        )

        contenido_recortado = False

        if len(body) > MAX_BODY_CHARS:
            body = (
                body[:MAX_BODY_CHARS]
                + "\n\n"
                + "[Contenido recortado por seguridad]"
            )

            contenido_recortado = True

        return MensajeDetalle(
            uid=str(uid_number),
            asunto=asunto,
            remitente_nombre=remitente_nombre,
            remitente_email=remitente_email,
            destinatarios=destinatarios,
            copia=copia,
            fecha=fecha,
            fecha_original=raw_date,
            cuerpo_texto=body,
            leido=leido,
            tamano_bytes=size,
            contenido_recortado=contenido_recortado,
            adjuntos=_extract_attachments(
                message
            ),
        )

    except (
        CorreoCryptoError,
        MensajeNoEncontrado,
        CorreoReaderError,
    ):
        raise
    except Exception as exc:
        raise CorreoReaderError(
            (
                "No se pudo leer el mensaje. "
                + _safe_error(
                    exc,
                    password,
                )
            )
        ) from exc
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


def cambiar_estado_lectura(
    cuenta: CuentaCorreo,
    uid: int | str,
    leido: bool,
    timeout: int = 15,
) -> ResultadoEstadoLectura:
    """
    Modifica exclusivamente la bandera IMAP \\Seen.

    No realiza una comprobación FETCH previa porque algunos
    servidores IMAP devuelven esa comprobación en un formato
    distinto al contenido de mensaje. UID STORE es la operación
    autoritativa para cambiar la bandera.
    """
    if not cuenta.activa:
        raise CorreoReaderError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoReaderError(
            "La conexión con IONOS no está verificada."
        )

    try:
        uid_number = int(uid)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MensajeNoEncontrado(
            "El identificador del mensaje no es válido."
        ) from exc

    if uid_number <= 0:
        raise MensajeNoEncontrado(
            "El identificador del mensaje no es válido."
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
            readonly=False,
        )

        if status != "OK":
            raise CorreoReaderError(
                "IONOS no permitió modificar la bandeja."
            )

        operation = (
            "+FLAGS.SILENT"
            if leido
            else "-FLAGS.SILENT"
        )

        status, store_data = imap.uid(
            "store",
            str(uid_number),
            operation,
            "(\\Seen)",
        )

        if status != "OK":
            raise CorreoReaderError(
                "IONOS no permitió cambiar el estado."
            )

        # Algunos servidores devuelven None aunque UID STORE
        # haya sido aceptado. El estado OK es el resultado
        # autoritativo; no se interpreta store_data como error.
        del store_data

        status, unseen_data = imap.uid(
            "search",
            None,
            "UNSEEN",
        )

        if status == "OK" and unseen_data:
            unseen_uids = (
                unseen_data[0].split()
                if unseen_data[0]
                else []
            )

            no_leidos = len(
                unseen_uids
            )
        else:
            no_leidos = 0

        return ResultadoEstadoLectura(
            uid=str(uid_number),
            leido=bool(leido),
            no_leidos=no_leidos,
        )

    except (
        CorreoCryptoError,
        MensajeNoEncontrado,
        CorreoReaderError,
    ):
        raise
    except Exception as exc:
        raise CorreoReaderError(
            (
                "No se pudo cambiar el estado. "
                + _safe_error(
                    exc,
                    password,
                )
            )
        ) from exc
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass
