import re
import secrets
from email.utils import getaddresses

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.http import (
    Http404,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from .attachments import (
    AdjuntoContenido,
    obtener_adjunto,
)
from .models import CuentaCorreo
from .reader import (
    CorreoReaderError,
    MensajeNoEncontrado,
    cambiar_estado_lectura,
    obtener_mensaje,
)
from .sender import (
    CorreoSendError,
    CorreoValidationError,
    enviar_correo,
)
from .services import (
    CorreoImapError,
    listar_bandeja,
)


NONCE_SESSION_KEY = "correo_compose_nonces"


def _cuenta_del_usuario(
    request,
) -> CuentaCorreo:
    cuenta = (
        CuentaCorreo.objects.filter(
            usuario=request.user,
            activa=True,
            verificada=True,
        )
        .select_related("usuario")
        .first()
    )

    if cuenta is None:
        raise Http404(
            "Cuenta de correo no disponible."
        )

    return cuenta


def _json_private(
    payload,
    *,
    status=200,
):
    response = JsonResponse(
        payload,
        status=status,
    )

    response["Cache-Control"] = (
        "private, no-store, no-cache, "
        "must-revalidate, max-age=0"
    )

    response["Pragma"] = "no-cache"

    return response


def _new_compose_nonce(
    request,
) -> str:
    existing = request.session.get(
        NONCE_SESSION_KEY,
        [],
    )

    tokens = [
        token
        for token in existing
        if isinstance(token, str)
    ][-9:]

    token = secrets.token_urlsafe(24)

    tokens.append(token)

    request.session[
        NONCE_SESSION_KEY
    ] = tokens

    request.session.modified = True

    return token


def _nonce_is_valid(
    request,
    token: str,
) -> bool:
    tokens = request.session.get(
        NONCE_SESSION_KEY,
        [],
    )

    return (
        isinstance(token, str)
        and bool(token)
        and token in tokens
    )


def _consume_nonce(
    request,
    token: str,
) -> None:
    tokens = request.session.get(
        NONCE_SESSION_KEY,
        [],
    )

    request.session[
        NONCE_SESSION_KEY
    ] = [
        value
        for value in tokens
        if value != token
    ]

    request.session.modified = True


def _header_addresses(
    value: str,
) -> list[str]:
    return [
        address.strip()
        for _, address in getaddresses(
            [value or ""]
        )
        if address.strip()
    ]


def _unique_emails(
    values,
    *,
    excluded=(),
):
    seen = {
        value.casefold()
        for value in excluded
        if value
    }

    result = []

    for value in values:
        value = (
            value
            or ""
        ).strip()

        if not value:
            continue

        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def _reply_subject(
    subject: str,
) -> str:
    subject = (
        subject
        or "(Sin asunto)"
    ).strip()

    if re.match(
        r"^\s*(re|aw|sv)\s*:",
        subject,
        flags=re.IGNORECASE,
    ):
        return subject

    return f"Re: {subject}"


def _forward_subject(
    subject: str,
) -> str:
    subject = (
        subject
        or "(Sin asunto)"
    ).strip()

    if re.match(
        r"^\s*(fwd|fw|rv|wg)\s*:",
        subject,
        flags=re.IGNORECASE,
    ):
        return subject

    return f"RV: {subject}"


def _quoted_reply_body(
    mensaje,
    fecha_display: str,
) -> str:
    source = (
        mensaje.cuerpo_texto
        or ""
    )[:12_000]

    quoted = "\n".join(
        (
            f"> {line}"
            if line
            else ">"
        )
        for line in source.splitlines()
    )

    return (
        "\n\n"
        f"El {fecha_display}, "
        f"{mensaje.remitente_nombre} escribió:\n"
        f"{quoted}"
    )


def _forward_body(
    mensaje,
    fecha_display: str,
) -> str:
    source = (
        mensaje.cuerpo_texto
        or ""
    )[:20_000]

    sender = mensaje.remitente_nombre

    if mensaje.remitente_email:
        sender += (
            f" <{mensaje.remitente_email}>"
        )

    return (
        "\n\n"
        "---------- Mensaje reenviado ----------\n"
        f"De: {sender}\n"
        f"Fecha: {fecha_display}\n"
        f"Asunto: {mensaje.asunto}\n"
        f"Para: {mensaje.destinatarios}\n"
        "\n"
        f"{source}"
    )


# INTASA_CORREO_V1F2_SAMEORIGIN_MENU
@xframe_options_sameorigin
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
def inicio(request):
    cuenta = (
        CuentaCorreo.objects.filter(
            usuario=request.user,
            activa=True,
        )
        .select_related("usuario")
        .first()
    )

    bandeja = None
    correo_error = ""
    compose_nonce = ""

    dock_mode = str(
        request.GET.get(
            "dock",
            "",
        )
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
    }

    if cuenta is not None:
        try:
            bandeja = listar_bandeja(
                cuenta,
                limit=20,
            )
        except CorreoImapError as exc:
            correo_error = str(exc)

        if (
            cuenta.verificada
            and cuenta.tiene_contrasena
        ):
            compose_nonce = (
                _new_compose_nonce(
                    request
                )
            )

    return render(
        request,
        "correo/inicio.html",
        {
            "cuenta_correo": cuenta,
            "bandeja": bandeja,
            "correo_error": correo_error,
            "compose_nonce": compose_nonce,
            "dock_mode": dock_mode,
        },
    )


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_GET
def detalle_mensaje(
    request,
    uid,
):
    cuenta = _cuenta_del_usuario(
        request
    )

    try:
        mensaje = obtener_mensaje(
            cuenta,
            uid,
        )
    except MensajeNoEncontrado as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=404,
        )
    except CorreoReaderError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

    fecha_display = (
        mensaje.fecha.strftime(
            "%d/%m/%Y %H:%M"
        )
        if mensaje.fecha
        else (
            mensaje.fecha_original
            or "Fecha no disponible"
        )
    )

    own_address = cuenta.direccion.casefold()

    to_addresses = _header_addresses(
        mensaje.destinatarios
    )

    cc_addresses = _header_addresses(
        mensaje.copia
    )

    reply_to = _unique_emails(
        [
            mensaje.remitente_email,
        ],
        excluded=[
            own_address,
        ],
    )

    reply_all_to = _unique_emails(
        [
            mensaje.remitente_email,
            *to_addresses,
        ],
        excluded=[
            own_address,
        ],
    )

    reply_all_cc = _unique_emails(
        cc_addresses,
        excluded=[
            own_address,
            *reply_all_to,
        ],
    )

    can_save_to_files = bool(
        request.user.is_superuser
        or request.user.is_staff
    )

    return _json_private(
        {
            "ok": True,
            "mensaje": {
                "uid": mensaje.uid,
                "asunto": mensaje.asunto,
                "remitente_nombre": (
                    mensaje.remitente_nombre
                ),
                "remitente_email": (
                    mensaje.remitente_email
                ),
                "destinatarios": (
                    mensaje.destinatarios
                ),
                "copia": mensaje.copia,
                "fecha": fecha_display,
                "cuerpo_texto": (
                    mensaje.cuerpo_texto
                ),
                "leido": mensaje.leido,
                "tamano_bytes": (
                    mensaje.tamano_bytes
                ),
                "contenido_recortado": (
                    mensaje.contenido_recortado
                ),
                "adjuntos": [
                    {
                        "indice": indice,
                        "nombre": adjunto.nombre,
                        "tipo_contenido": (
                            adjunto.tipo_contenido
                        ),
                        "tamano_bytes": (
                            adjunto.tamano_bytes
                        ),
                        "download_url": reverse(
                            "correo:descargar_adjunto",
                            args=(
                                uid,
                                indice,
                            ),
                        ),
                        "save_url": (
                            reverse(
                                (
                                    "correo:"
                                    "guardar_adjunto_archivos"
                                ),
                                args=(
                                    uid,
                                    indice,
                                ),
                            )
                            if can_save_to_files
                            else ""
                        ),
                    }
                    for indice, adjunto
                    in enumerate(
                        mensaje.adjuntos
                    )
                ],
                "componer": {
                    "reply_to": ", ".join(
                        reply_to
                    ),
                    "reply_all_to": ", ".join(
                        reply_all_to
                    ),
                    "reply_all_cc": ", ".join(
                        reply_all_cc
                    ),
                    "reply_subject": (
                        _reply_subject(
                            mensaje.asunto
                        )
                    ),
                    "forward_subject": (
                        _forward_subject(
                            mensaje.asunto
                        )
                    ),
                    "reply_body": (
                        _quoted_reply_body(
                            mensaje,
                            fecha_display,
                        )
                    ),
                    "forward_body": (
                        _forward_body(
                            mensaje,
                            fecha_display,
                        )
                    ),
                },
            },
        }
    )


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_POST
def estado_mensaje(
    request,
    uid,
):
    cuenta = _cuenta_del_usuario(
        request
    )

    raw_leido = request.POST.get(
        "leido",
        "",
    ).strip().lower()

    if raw_leido in (
        "1",
        "true",
        "si",
        "sí",
    ):
        leido = True

    elif raw_leido in (
        "0",
        "false",
        "no",
    ):
        leido = False

    else:
        return _json_private(
            {
                "ok": False,
                "error": (
                    "El estado de lectura "
                    "no es válido."
                ),
            },
            status=400,
        )

    try:
        resultado = cambiar_estado_lectura(
            cuenta,
            uid,
            leido,
        )
    except MensajeNoEncontrado as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=404,
        )
    except CorreoReaderError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

    return _json_private(
        {
            "ok": True,
            "uid": resultado.uid,
            "leido": resultado.leido,
            "no_leidos": resultado.no_leidos,
        }
    )


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_POST
def enviar_mensaje(
    request,
):
    cuenta = _cuenta_del_usuario(
        request
    )

    nonce = request.POST.get(
        "nonce",
        "",
    )

    if not _nonce_is_valid(
        request,
        nonce,
    ):
        return _json_private(
            {
                "ok": False,
                "error": (
                    "La solicitud de envío ha caducado "
                    "o ya fue utilizada. Actualiza la "
                    "página antes de volver a enviar."
                ),
            },
            status=409,
        )

    mode = request.POST.get(
        "modo",
        "nuevo",
    ).strip().lower()

    if mode not in {
        "nuevo",
        "responder",
        "responder_todos",
        "reenviar",
    }:
        return _json_private(
            {
                "ok": False,
                "error": (
                    "El modo de redacción "
                    "no es válido."
                ),
            },
            status=400,
        )

    try:
        resultado = enviar_correo(
            cuenta,
            para=request.POST.get(
                "para",
                "",
            ),
            copia=request.POST.get(
                "copia",
                "",
            ),
            copia_oculta=request.POST.get(
                "copia_oculta",
                "",
            ),
            asunto=request.POST.get(
                "asunto",
                "",
            ),
            cuerpo=request.POST.get(
                "cuerpo",
                "",
            ),
            adjuntos=request.FILES.getlist(
                "adjuntos"
            ),
        )

    except CorreoValidationError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=400,
        )

    except CorreoSendError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

    _consume_nonce(
        request,
        nonce,
    )

    next_nonce = _new_compose_nonce(
        request
    )

    return _json_private(
        {
            "ok": True,
            "message_id": (
                resultado.message_id
            ),
            "copia_enviados": (
                resultado.copia_enviados
            ),
            "carpeta_enviados": (
                resultado.carpeta_enviados
            ),
            "advertencia": (
                resultado.advertencia
            ),
            "next_nonce": next_nonce,
        }
    )


# INTASA_CORREO_V1E1_ATTACHMENTS
def _puede_gestionar_archivos_cloud(
    user,
) -> bool:
    """
    Mantiene la misma política que el explorador cloud actual.
    """
    return bool(
        getattr(
            user,
            "is_authenticated",
            False,
        )
        and (
            getattr(
                user,
                "is_superuser",
                False,
            )
            or getattr(
                user,
                "is_staff",
                False,
            )
        )
    )


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_GET
def descargar_adjunto(
    request,
    uid,
    indice,
):
    from django.http import HttpResponse
    from django.utils.http import (
        content_disposition_header,
    )

    cuenta = _cuenta_del_usuario(
        request
    )

    try:
        adjunto = obtener_adjunto(
            cuenta,
            uid,
            indice,
        )

    except MensajeNoEncontrado as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=404,
        )

    except CorreoReaderError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

    response = HttpResponse(
        adjunto.contenido,
        content_type=(
            adjunto.tipo_contenido
            or "application/octet-stream"
        ),
    )

    response["Content-Disposition"] = (
        content_disposition_header(
            True,
            adjunto.nombre,
        )
    )

    response["Content-Length"] = str(
        adjunto.tamano_bytes
    )

    response["X-Content-Type-Options"] = (
        "nosniff"
    )

    response["Cache-Control"] = (
        "private, no-store, no-cache, "
        "must-revalidate, max-age=0"
    )

    response["Pragma"] = "no-cache"

    return response


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_GET
def carpetas_archivos(
    request,
):
    from archivos.cloud_gateway import (
        CloudGatewayError,
        NextcloudCloudGateway,
    )

    if not _puede_gestionar_archivos_cloud(
        request.user
    ):
        return _json_private(
            {
                "ok": False,
                "error": (
                    "No tienes permisos para gestionar "
                    "el almacenamiento documental."
                ),
            },
            status=403,
        )

    gateway = NextcloudCloudGateway()

    try:
        current_path = gateway.normalize_path(
            request.GET.get(
                "path",
                "",
            ),
            allow_empty=True,
        )

        items = gateway.list_directory(
            current_path
        )

        hidden_names = set()

        if not current_path:
            configured_hidden = (
                gateway.config.get(
                    "hidden_root_items"
                )
                or []
            )

            if isinstance(
                configured_hidden,
                list,
            ):
                hidden_names = {
                    str(value).casefold()
                    for value
                    in configured_hidden
                }

        folders = []

        for item in items:
            if not item.get(
                "is_folder"
            ):
                continue

            name = str(
                item.get("name")
                or ""
            ).strip()

            storage_key = str(
                item.get("storage_key")
                or ""
            ).strip("/")

            if not name or not storage_key:
                continue

            if (
                not current_path
                and name.casefold()
                in hidden_names
            ):
                continue

            folders.append(
                {
                    "name": name,
                    "path": storage_key,
                }
            )

        folders.sort(
            key=lambda item: (
                item["name"].casefold()
            )
        )

        parent_path = (
            "/".join(
                current_path.split("/")[:-1]
            )
            if current_path
            else ""
        )

        return _json_private(
            {
                "ok": True,
                "current_path": current_path,
                "parent_path": parent_path,
                "folders": folders,
            }
        )

    except (
        CloudGatewayError,
        FileNotFoundError,
    ) as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=409,
        )


@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_POST
def guardar_adjunto_archivos(
    request,
    uid,
    indice,
):
    import logging
    from urllib.parse import urlencode

    from django.core.files.uploadedfile import (
        SimpleUploadedFile,
    )

    from archivos.activity import (
        registrar_subida_documental,
    )

    from archivos.cloud_gateway import (
        CloudGatewayError,
        NextcloudCloudGateway,
    )

    from archivos.cloud_references import (
        CloudReferenceError,
        upsert_cloud_uploaded_reference,
    )

    from archivos.cloud_views import (
        _cloud_index_folder,
    )

    from archivos.team_scope import (
        DocumentTeamResolutionError,
        resolve_document_team,
    )

    logger = logging.getLogger(
        __name__
    )

    if not _puede_gestionar_archivos_cloud(
        request.user
    ):
        return _json_private(
            {
                "ok": False,
                "error": (
                    "No tienes permisos para guardar "
                    "adjuntos en Archivos INTASA."
                ),
            },
            status=403,
        )

    cuenta = _cuenta_del_usuario(
        request
    )

    gateway = NextcloudCloudGateway()

    try:
        parent_path = gateway.normalize_path(
            request.POST.get(
                "path",
                "",
            ),
            allow_empty=True,
        )

        adjunto = obtener_adjunto(
            cuenta,
            uid,
            indice,
        )

        team = resolve_document_team(
            request
        )

        cloud_index_folder = (
            _cloud_index_folder()
        )

        uploaded_file = SimpleUploadedFile(
            name=adjunto.nombre,
            content=adjunto.contenido,
            content_type=(
                adjunto.tipo_contenido
                or "application/octet-stream"
            ),
        )

        item = gateway.upload_file(
            parent_path,
            uploaded_file,
        )

        try:
            archivo, created = (
                upsert_cloud_uploaded_reference(
                    folder=cloud_index_folder,
                    item=item,
                    actor=request.user,
                    team=team,
                )
            )

        except CloudReferenceError as exc:
            return _json_private(
                {
                    "ok": False,
                    "error": (
                        "El adjunto se guardó en INTASA "
                        "Cloud, pero no pudo indexarse "
                        f"en el Portal: {exc}"
                    ),
                    "remote_saved": True,
                },
                status=502,
            )

        cloud_url = reverse(
            "archivos:explorador_raiz"
        )

        if parent_path:
            cloud_url += (
                "?"
                + urlencode(
                    {
                        "path": parent_path,
                    }
                )
            )

        warning = ""

        try:
            registrar_subida_documental(
                actor=request.user,
                team=team,
                archivos=[
                    archivo,
                ],
                destino=(
                    parent_path
                    or "Archivos"
                ),
                url=cloud_url,
                storage_provider="nextcloud",
            )

        except Exception:
            logger.exception(
                (
                    "No se pudo registrar la actividad "
                    "del adjunto guardado desde correo."
                ),
                extra={
                    "actor_id": request.user.pk,
                    "team_id": team.pk,
                    "archivo_id": archivo.pk,
                    "uid": uid,
                    "indice": indice,
                },
            )

            warning = (
                "El archivo se guardó correctamente, "
                "pero la actividad no pudo incorporarse "
                "al panel."
            )

        return _json_private(
            {
                "ok": True,
                "archivo_id": archivo.pk,
                "created": bool(created),
                "nombre": archivo.nombre_original,
                "storage_key": archivo.storage_key,
                "cloud_url": cloud_url,
                "archivo_url": reverse(
                    "archivos:archivo_detalle",
                    kwargs={
                        "pk": archivo.pk,
                    },
                ),
                "warning": warning,
            }
        )

    except MensajeNoEncontrado as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=404,
        )

    except CorreoReaderError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

    except DocumentTeamResolutionError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=409,
        )

    except (
        CloudGatewayError,
        FileNotFoundError,
    ) as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=409,
        )


# INTASA_CORREO_V1F1_FLOATING_DOCK
@never_cache
@login_required
@permission_required(
    "correo.use_correo",
    raise_exception=True,
)
@require_GET
def contador_flotante(request):
    from .services import (
        obtener_contadores_bandeja,
    )

    cuenta = _cuenta_del_usuario(
        request
    )

    try:
        counters = obtener_contadores_bandeja(
            cuenta
        )

        return _json_private(
            {
                "ok": True,
                "no_leidos": int(
                    counters["no_leidos"]
                ),
                "total_mensajes": int(
                    counters["total_mensajes"]
                ),
                "direccion": cuenta.direccion,
            }
        )

    except CorreoImapError as exc:
        return _json_private(
            {
                "ok": False,
                "error": str(exc),
            },
            status=502,
        )

