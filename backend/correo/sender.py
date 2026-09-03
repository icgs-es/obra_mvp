import imaplib
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as datetime_timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import (
    format_datetime,
    formataddr,
    getaddresses,
    make_msgid,
)

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .crypto import CorreoCryptoError
from .models import CuentaCorreo


MAX_RECIPIENTS = 50
MAX_SUBJECT_CHARS = 500
MAX_BODY_CHARS = 250_000


class CorreoSendError(RuntimeError):
    """Error seguro durante el envío de correo."""


class CorreoValidationError(CorreoSendError):
    """Datos de redacción no válidos."""


@dataclass(frozen=True)
class ResultadoEnvio:
    message_id: str
    copia_enviados: bool
    carpeta_enviados: str
    advertencia: str


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
    )[:1200]


def normalizar_destinatarios(
    raw_value: str,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    raw_value = (
        raw_value
        or ""
    ).strip()

    if not raw_value:
        if required:
            raise CorreoValidationError(
                "Debes indicar al menos un destinatario."
            )

        return ()

    parsed = getaddresses(
        [
            raw_value.replace(
                ";",
                ",",
            )
        ]
    )

    result: list[str] = []
    seen: set[str] = set()

    for _, address in parsed:
        address = address.strip()

        if not address:
            continue

        try:
            validate_email(
                address
            )
        except ValidationError as exc:
            raise CorreoValidationError(
                (
                    "La dirección de correo "
                    f"«{address}» no es válida."
                )
            ) from exc

        key = address.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(address)

    if required and not result:
        raise CorreoValidationError(
            "Debes indicar al menos un destinatario."
        )

    if len(result) > MAX_RECIPIENTS:
        raise CorreoValidationError(
            (
                "El mensaje supera el máximo "
                f"de {MAX_RECIPIENTS} destinatarios."
            )
        )

    return tuple(result)


def _validate_subject(
    subject: str,
) -> str:
    subject = (
        subject
        or ""
    ).strip()

    if "\r" in subject or "\n" in subject:
        raise CorreoValidationError(
            "El asunto contiene caracteres no válidos."
        )

    if len(subject) > MAX_SUBJECT_CHARS:
        raise CorreoValidationError(
            (
                "El asunto supera el límite "
                f"de {MAX_SUBJECT_CHARS} caracteres."
            )
        )

    return subject or "(Sin asunto)"


def _validate_body(
    body: str,
) -> str:
    body = (
        body
        or ""
    ).replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    if len(body) > MAX_BODY_CHARS:
        raise CorreoValidationError(
            (
                "El cuerpo supera el límite "
                f"de {MAX_BODY_CHARS} caracteres."
            )
        )

    return body


def _unquote_mailbox(
    value: bytes,
) -> bytes:
    value = value.strip()

    if (
        len(value) >= 2
        and value.startswith(b'"')
        and value.endswith(b'"')
    ):
        value = value[1:-1]

        value = value.replace(
            b'\\"',
            b'"',
        ).replace(
            b"\\\\",
            b"\\",
        )

    return value


def _quote_mailbox_arg(
    value: bytes,
) -> bytes:
    """
    Protege un nombre de carpeta como argumento IMAP.

    IMAP requiere comillas cuando la carpeta contiene
    espacios, por ejemplo: "Elementos enviados".
    """
    escaped = value.replace(
        b"\\",
        b"\\\\",
    ).replace(
        b'"',
        b'\\"',
    )

    return (
        b'"'
        + escaped
        + b'"'
    )


def _parse_list_line(
    line,
) -> tuple[bytes, bytes] | None:
    if not isinstance(line, bytes):
        return None

    match = re.match(
        rb'^'
        rb'\((?P<flags>[^)]*)\)'
        rb'\s+'
        rb'(?:NIL|"(?:\\.|[^"])*")'
        rb'\s+'
        rb'(?P<name>.+)'
        rb'$',
        line.strip(),
    )

    if not match:
        return None

    return (
        match.group("flags"),
        _unquote_mailbox(
            match.group("name")
        ),
    )


def _find_sent_mailbox(
    imap,
) -> bytes | None:
    status, lines = imap.list()

    parsed: list[
        tuple[bytes, bytes]
    ] = []

    if status == "OK" and lines:
        for line in lines:
            mailbox_data = _parse_list_line(
                line
            )

            if mailbox_data is None:
                continue

            parsed.append(
                mailbox_data
            )

            flags, mailbox = mailbox_data

            if b"\\Sent" in flags:
                return mailbox

    common_names = (
        b"Sent",
        b"Sent Items",
        b"Sent Messages",
        b"INBOX.Sent",
        b"Enviados",
        b"Elementos enviados",
    )

    existing_names = {
        mailbox.casefold()
        for _, mailbox in parsed
    }

    for candidate in common_names:
        if candidate.casefold() in existing_names:
            return candidate

    for candidate in common_names:
        try:
            status, _ = imap.status(
                _quote_mailbox_arg(
                    candidate
                ),
                "(MESSAGES)",
            )
        except Exception:
            continue

        if status == "OK":
            return candidate

    return None


def _mailbox_display(
    mailbox: bytes | None,
) -> str:
    if not mailbox:
        return ""

    try:
        return mailbox.decode("utf-8")
    except UnicodeDecodeError:
        return mailbox.decode(
            "latin-1",
            errors="replace",
        )


def _open_imap(
    cuenta: CuentaCorreo,
    password: str,
    timeout: int,
):
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

    return imap


def diagnosticar_carpeta_enviados(
    cuenta: CuentaCorreo,
    timeout: int = 15,
) -> str:
    if not cuenta.activa:
        raise CorreoSendError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoSendError(
            "La conexión con IONOS no está verificada."
        )

    try:
        password = cuenta.get_password()
    except CorreoCryptoError as exc:
        raise CorreoSendError(
            str(exc)
        ) from exc

    imap = None

    try:
        imap = _open_imap(
            cuenta,
            password,
            timeout,
        )

        mailbox = _find_sent_mailbox(
            imap
        )

        if mailbox is None:
            raise CorreoSendError(
                (
                    "No se localizó la carpeta "
                    "Enviados en IONOS."
                )
            )

        return _mailbox_display(
            mailbox
        )

    except CorreoSendError:
        raise
    except Exception as exc:
        raise CorreoSendError(
            (
                "No se pudo localizar la carpeta "
                "Enviados. "
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



# INTASA_CORREO_V1E2_OUTBOUND_ATTACHMENTS
MAX_OUTBOUND_ATTACHMENTS = 10
MAX_OUTBOUND_ATTACHMENTS_BYTES = (
    12 * 1024 * 1024
)


def preparar_adjuntos_salida(
    files,
):
    """
    Valida y carga los adjuntos salientes sin persistirlos.

    Máximo 10 archivos y 12 MB totales antes de la
    codificación MIME.
    """
    import mimetypes
    import re

    from .attachments import (
        nombre_adjunto_seguro,
    )

    files = list(
        files or ()
    )

    if len(files) > MAX_OUTBOUND_ATTACHMENTS:
        raise CorreoValidationError(
            (
                "Solo se pueden adjuntar hasta "
                f"{MAX_OUTBOUND_ATTACHMENTS} archivos."
            )
        )

    prepared = []
    total_size = 0

    for uploaded_file in files:
        raw_name = str(
            getattr(
                uploaded_file,
                "name",
                "",
            )
            or ""
        )

        filename = nombre_adjunto_seguro(
            raw_name
        )

        declared_size = getattr(
            uploaded_file,
            "size",
            None,
        )

        if declared_size is not None:
            try:
                declared_size = int(
                    declared_size
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise CorreoValidationError(
                    (
                        f"El tamaño de «{filename}» "
                        "no es válido."
                    )
                ) from exc

            if declared_size < 0:
                raise CorreoValidationError(
                    (
                        f"El tamaño de «{filename}» "
                        "no es válido."
                    )
                )

            if (
                total_size
                + declared_size
                > MAX_OUTBOUND_ATTACHMENTS_BYTES
            ):
                raise CorreoValidationError(
                    (
                        "Los adjuntos superan el máximo "
                        "total de 12 MB."
                    )
                )

        try:
            uploaded_file.seek(0)
        except (
            AttributeError,
            OSError,
        ):
            pass

        try:
            content = uploaded_file.read()
        except Exception as exc:
            raise CorreoValidationError(
                (
                    f"No se pudo leer «{filename}»."
                )
            ) from exc

        if not isinstance(
            content,
            bytes,
        ):
            raise CorreoValidationError(
                (
                    f"El contenido de «{filename}» "
                    "no es válido."
                )
            )

        actual_size = len(content)

        if (
            total_size
            + actual_size
            > MAX_OUTBOUND_ATTACHMENTS_BYTES
        ):
            raise CorreoValidationError(
                (
                    "Los adjuntos superan el máximo "
                    "total de 12 MB."
                )
            )

        total_size += actual_size

        content_type = str(
            getattr(
                uploaded_file,
                "content_type",
                "",
            )
            or ""
        ).strip().lower()

        content_type = content_type.split(
            ";",
            1,
        )[0].strip()

        valid_content_type = re.fullmatch(
            (
                r"[a-z0-9!#$&^_.+-]+/"
                r"[a-z0-9!#$&^_.+-]+"
            ),
            content_type,
        )

        if not valid_content_type:
            content_type = (
                mimetypes.guess_type(
                    filename
                )[0]
                or "application/octet-stream"
            )

        maintype, subtype = content_type.split(
            "/",
            1,
        )

        if maintype == "multipart":
            maintype = "application"
            subtype = "octet-stream"
            content_type = (
                "application/octet-stream"
            )

        prepared.append(
            {
                "nombre": filename,
                "tipo_contenido": content_type,
                "maintype": maintype,
                "subtype": subtype,
                "tamano_bytes": actual_size,
                "contenido": content,
            }
        )

    return tuple(
        prepared
    )


def agregar_adjuntos_mensaje(
    message,
    attachments,
) -> None:
    for attachment in attachments:
        message.add_attachment(
            attachment["contenido"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["nombre"],
        )


def enviar_correo(
    cuenta: CuentaCorreo,
    *,
    para: str,
    copia: str = "",
    copia_oculta: str = "",
    asunto: str,
    cuerpo: str,
    adjuntos=(),
    timeout: int = 20,
) -> ResultadoEnvio:
    if not cuenta.activa:
        raise CorreoSendError(
            "La cuenta de correo está desactivada."
        )

    if not cuenta.verificada:
        raise CorreoSendError(
            "La conexión con IONOS no está verificada."
        )

    to_addresses = normalizar_destinatarios(
        para,
        required=True,
    )

    cc_addresses = normalizar_destinatarios(
        copia,
    )

    bcc_addresses = normalizar_destinatarios(
        copia_oculta,
    )

    recipients: list[str] = []
    recipient_keys: set[str] = set()

    for address in (
        *to_addresses,
        *cc_addresses,
        *bcc_addresses,
    ):
        key = address.casefold()

        if key in recipient_keys:
            continue

        recipient_keys.add(key)
        recipients.append(address)

    if len(recipients) > MAX_RECIPIENTS:
        raise CorreoValidationError(
            (
                "El mensaje supera el máximo "
                f"de {MAX_RECIPIENTS} destinatarios."
            )
        )

    subject = _validate_subject(
        asunto
    )

    body = _validate_body(
        cuerpo
    )

    prepared_attachments = (
        preparar_adjuntos_salida(
            adjuntos
        )
    )

    try:
        password = cuenta.get_password()
    except CorreoCryptoError as exc:
        raise CorreoSendError(
            str(exc)
        ) from exc

    domain = (
        cuenta.direccion.rsplit(
            "@",
            1,
        )[-1]
        if "@" in cuenta.direccion
        else None
    )

    message = EmailMessage(
        policy=SMTP
    )

    display_name = (
        cuenta.nombre_remitente
        or cuenta.usuario.get_full_name()
        or cuenta.usuario.get_username()
    )

    message["From"] = formataddr(
        (
            display_name,
            cuenta.direccion,
        )
    )

    message["To"] = ", ".join(
        to_addresses
    )

    if cc_addresses:
        message["Cc"] = ", ".join(
            cc_addresses
        )

    message["Subject"] = subject

    message["Date"] = format_datetime(
        datetime.now(
            datetime_timezone.utc
        )
    )

    message_id = make_msgid(
        domain=domain,
    )

    message["Message-ID"] = message_id

    message.set_content(
        body,
        subtype="plain",
        charset="utf-8",
    )

    agregar_adjuntos_mensaje(
        message,
        prepared_attachments,
    )

    smtp = None

    try:
        context = ssl.create_default_context()

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

        smtp.send_message(
            message,
            from_addr=cuenta.direccion,
            to_addrs=recipients,
        )

    except Exception as exc:
        raise CorreoSendError(
            (
                "IONOS no pudo enviar el mensaje. "
                + _safe_error(
                    exc,
                    password,
                )
            )
        ) from exc

    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass

    raw_message = message.as_bytes(
        policy=SMTP
    )

    imap = None
    sent_mailbox = None
    copia_enviados = False
    advertencia = ""

    try:
        imap = _open_imap(
            cuenta,
            password,
            timeout,
        )

        sent_mailbox = _find_sent_mailbox(
            imap
        )

        if sent_mailbox is None:
            advertencia = (
                "El correo se envió correctamente, "
                "pero no se localizó la carpeta Enviados."
            )
        else:
            status, _ = imap.append(
                _quote_mailbox_arg(
                    sent_mailbox
                ),
                "(\\Seen)",
                imaplib.Time2Internaldate(
                    time.time()
                ),
                raw_message,
            )

            if status == "OK":
                copia_enviados = True
            else:
                advertencia = (
                    "El correo se envió correctamente, "
                    "pero IONOS no confirmó la copia "
                    "en Enviados."
                )

    except Exception as exc:
        advertencia = (
            "El correo se envió correctamente, "
            "pero no se pudo guardar la copia "
            "en Enviados. "
            + _safe_error(
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

    return ResultadoEnvio(
        message_id=message_id,
        copia_enviados=copia_enviados,
        carpeta_enviados=_mailbox_display(
            sent_mailbox
        ),
        advertencia=advertencia,
    )
