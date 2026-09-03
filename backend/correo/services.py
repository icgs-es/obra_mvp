import imaplib
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime

from django.utils import timezone

from .crypto import CorreoCryptoError
from .models import CuentaCorreo


@dataclass(frozen=True)
class ResultadoConexion:
    correcta: bool
    imap_correcto: bool
    smtp_correcto: bool
    detalle: str


@dataclass(frozen=True)
class MensajeResumen:
    uid: str
    asunto: str
    remitente_nombre: str
    remitente_email: str
    fecha: datetime | None
    fecha_original: str
    leido: bool
    tamano_bytes: int


@dataclass(frozen=True)
class ResultadoBandeja:
    mensajes: tuple[MensajeResumen, ...]
    no_leidos: int
    total_mensajes: int


class CorreoImapError(RuntimeError):
    """Error seguro al consultar el buzón IMAP."""


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

    return f"{type(exc).__name__}: {text}"[:1000]


def _decode_header_value(
    raw_value: str | None,
) -> str:
    if not raw_value:
        return ""

    parts: list[str] = []

    for value, encoding in decode_header(
        raw_value
    ):
        if isinstance(value, bytes):
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

        parts.append(decoded)

    return "".join(parts).strip()


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

        if timezone.is_naive(value):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return timezone.localtime(value)
    except Exception:
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


def probar_conexion(
    cuenta: CuentaCorreo,
    timeout: int = 15,
) -> ResultadoConexion:
    if not cuenta.activa:
        return ResultadoConexion(
            correcta=False,
            imap_correcto=False,
            smtp_correcto=False,
            detalle="La cuenta está desactivada.",
        )

    try:
        password = cuenta.get_password()
    except CorreoCryptoError as exc:
        return ResultadoConexion(
            correcta=False,
            imap_correcto=False,
            smtp_correcto=False,
            detalle=str(exc),
        )

    context = ssl.create_default_context()
    imap_correcto = False
    smtp_correcto = False
    errores: list[str] = []

    imap = None

    try:
        imap = imaplib.IMAP4_SSL(
            host=cuenta.imap_host,
            port=cuenta.imap_port,
            ssl_context=context,
            timeout=timeout,
        )

        imap.login(
            cuenta.direccion,
            password,
        )

        imap_correcto = True
    except Exception as exc:
        errores.append(
            "IMAP: " + _safe_error(
                exc,
                password,
            )
        )
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass

    smtp = None

    try:
        smtp = smtplib.SMTP_SSL(
            host=cuenta.smtp_host,
            port=cuenta.smtp_port,
            context=context,
            timeout=timeout,
        )

        smtp.login(
            cuenta.direccion,
            password,
        )

        smtp_correcto = True
    except Exception as exc:
        errores.append(
            "SMTP: " + _safe_error(
                exc,
                password,
            )
        )
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass

    correcta = (
        imap_correcto
        and smtp_correcto
    )

    return ResultadoConexion(
        correcta=correcta,
        imap_correcto=imap_correcto,
        smtp_correcto=smtp_correcto,
        detalle=(
            "Conexión IMAP y SMTP correcta."
            if correcta
            else " | ".join(errores)
        ),
    )


def listar_bandeja(
    cuenta: CuentaCorreo,
    limit: int = 20,
    timeout: int = 12,
) -> ResultadoBandeja:
    if not cuenta.activa:
        raise CorreoImapError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoImapError(
            (
                "La conexión de la cuenta "
                "todavía no está verificada."
            )
        )

    safe_limit = max(
        1,
        min(int(limit), 50),
    )

    imap = None
    password = ""

    try:
        imap, password = _open_imap(
            cuenta,
            timeout,
        )

        status, select_data = imap.select(
            "INBOX",
            readonly=True,
        )

        if status != "OK":
            raise CorreoImapError(
                "IONOS no permitió abrir la bandeja de entrada."
            )

        total_mensajes = 0

        if select_data and select_data[0]:
            try:
                total_mensajes = int(
                    select_data[0]
                )
            except (
                TypeError,
                ValueError,
            ):
                total_mensajes = 0

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

        status, all_data = imap.uid(
            "search",
            None,
            "ALL",
        )

        if status != "OK":
            raise CorreoImapError(
                "IONOS no devolvió la lista de mensajes."
            )

        all_uids = (
            all_data[0].split()
            if all_data
            and all_data[0]
            else []
        )

        selected_uids = list(
            reversed(
                all_uids[-safe_limit:]
            )
        )

        if not selected_uids:
            return ResultadoBandeja(
                mensajes=(),
                no_leidos=no_leidos,
                total_mensajes=total_mensajes,
            )

        uid_set = b",".join(
            selected_uids
        ).decode("ascii")

        status, fetch_data = imap.uid(
            "fetch",
            uid_set,
            (
                "(BODY.PEEK[HEADER.FIELDS "
                "(SUBJECT FROM DATE MESSAGE-ID)] "
                "FLAGS RFC822.SIZE)"
            ),
        )

        if status != "OK":
            raise CorreoImapError(
                (
                    "IONOS no devolvió "
                    "las cabeceras de los mensajes."
                )
            )

        messages_by_uid: dict[
            str,
            MensajeResumen,
        ] = {}

        for item in fetch_data:
            if (
                not isinstance(item, tuple)
                or len(item) < 2
            ):
                continue

            metadata = item[0]

            if not isinstance(
                metadata,
                bytes,
            ):
                continue

            uid_match = re.search(
                rb"\bUID\s+(\d+)\b",
                metadata,
            )

            if not uid_match:
                continue

            uid = uid_match.group(
                1
            ).decode("ascii")

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

            raw_headers = item[1]

            if not isinstance(
                raw_headers,
                bytes,
            ):
                raw_headers = b""

            message = message_from_bytes(
                raw_headers,
                policy=default,
            )

            asunto = _decode_header_value(
                message.get("Subject")
            ) or "(Sin asunto)"

            remitente_raw = (
                _decode_header_value(
                    message.get("From")
                )
            )

            remitente_nombre, remitente_email = (
                parseaddr(remitente_raw)
            )

            remitente_nombre = (
                remitente_nombre.strip()
                or remitente_email
                or "Remitente desconocido"
            )

            raw_date = (
                message.get("Date")
                or ""
            )

            messages_by_uid[uid] = MensajeResumen(
                uid=uid,
                asunto=asunto,
                remitente_nombre=remitente_nombre,
                remitente_email=remitente_email,
                fecha=_parse_message_date(
                    raw_date
                ),
                fecha_original=raw_date,
                leido=leido,
                tamano_bytes=size,
            )

        ordered_messages: list[
            MensajeResumen
        ] = []

        for raw_uid in selected_uids:
            uid = raw_uid.decode(
                "ascii"
            )

            message = messages_by_uid.get(
                uid
            )

            if message is not None:
                ordered_messages.append(
                    message
                )

        return ResultadoBandeja(
            mensajes=tuple(
                ordered_messages
            ),
            no_leidos=no_leidos,
            total_mensajes=total_mensajes,
        )

    except CorreoCryptoError as exc:
        raise CorreoImapError(
            str(exc)
        ) from exc
    except CorreoImapError:
        raise
    except Exception as exc:
        safe_detail = _safe_error(
            exc,
            password,
        )

        raise CorreoImapError(
            (
                "No se pudo consultar IONOS. "
                f"{safe_detail}"
            )
        ) from exc
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


# INTASA_CORREO_V1F1_FLOATING_DOCK
def obtener_contadores_bandeja(
    cuenta: CuentaCorreo,
    timeout: int = 8,
) -> dict:
    """
    Obtiene únicamente total y no leídos.

    No descarga cabeceras ni cuerpos de mensajes.
    """
    if not cuenta.activa:
        raise CorreoImapError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoImapError(
            "La conexión de correo no está verificada."
        )

    imap = None
    password = ""

    try:
        imap, password = _open_imap(
            cuenta,
            timeout,
        )

        status, select_data = imap.select(
            "INBOX",
            readonly=True,
        )

        if status != "OK":
            raise CorreoImapError(
                "IONOS no permitió abrir la bandeja."
            )

        total_mensajes = 0

        if select_data and select_data[0]:
            try:
                total_mensajes = int(
                    select_data[0]
                )
            except (
                TypeError,
                ValueError,
            ):
                total_mensajes = 0

        status, unseen_data = imap.uid(
            "search",
            None,
            "UNSEEN",
        )

        if status != "OK":
            raise CorreoImapError(
                "IONOS no devolvió los mensajes sin leer."
            )

        unseen_uids = (
            unseen_data[0].split()
            if unseen_data
            and unseen_data[0]
            else []
        )

        return {
            "no_leidos": len(unseen_uids),
            "total_mensajes": total_mensajes,
        }

    except CorreoImapError:
        raise

    except Exception as exc:
        raise CorreoImapError(
            (
                "No se pudieron consultar los contadores. "
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
