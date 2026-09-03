from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.utils.http import content_disposition_header

from actividad.models import ActividadPlataforma
from actividad.services import registrar_actividad

from .forms import (
    CompartirConversacionForm,
    PreguntaIAForm,
)
from .models import (
    AccesoConversacionIA,
    ConversacionIA,
    MensajeIA,
    AdjuntoIA,
    ProcesamientoMensajeIA,
)
from .attachment_services import (
    create_attachments,
    schedule_physical_delete,
)
from .private_storage import private_ia_storage
from .provider_openai import (
    IAProviderError,
    obtener_estado_proveedor,
)
from .help_bridge import generar_respuesta_segura
from .tasks import process_document_message
from .suggestions import (
    SUGERENCIAS_ACTUALES,
    SUGERENCIAS_FUTURAS,
)


def _conversaciones_propias(user):
    return (
        ConversacionIA.objects
        .filter(user=user)
        .select_related("user")
        .order_by("-updated_at", "-id")
    )


def _conversaciones_compartidas(user):
    return (
        ConversacionIA.objects
        .filter(
            accesos_compartidos__user=user
        )
        .exclude(user=user)
        .select_related("user")
        .order_by("-updated_at", "-id")
        .distinct()
    )


def _conversacion_visible(user, pk):
    return get_object_or_404(
        ConversacionIA.objects
        .filter(
            Q(user=user)
            | Q(accesos_compartidos__user=user)
        )
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "mensajes",
                queryset=MensajeIA.objects.select_related(
                    "document_processing"
                ).prefetch_related("adjuntos"),
            ),
            "accesos_compartidos__user",
            "accesos_compartidos__shared_by",
        )
        .distinct(),
        pk=pk,
    )


def _mensaje_error_proveedor(code):
    messages_by_code = {
        "timeout": (
            "La respuesta ha tardado demasiado. "
            "Vuelve a intentarlo."
        ),
        "rate_limit": (
            "El servicio de IA está temporalmente "
            "ocupado. Vuelve a intentarlo más tarde."
        ),
        "authentication_error": (
            "La conexión de INTASA IA requiere revisión "
            "por parte del administrador."
        ),
        "permission_error": (
            "El proyecto OpenAI no permite utilizar "
            "el modelo configurado."
        ),
    }

    return messages_by_code.get(
        code,
        (
            "No se ha podido obtener una respuesta de "
            "INTASA IA. La consulta quedó registrada, "
            "pero no se modificó información empresarial."
        ),
    )


@login_required
@permission_required(
    "intasa_ia.use_intasa_ia",
    raise_exception=True,
)
def inicio(request, pk=None):
    conversaciones_propias = (
        _conversaciones_propias(request.user)
    )

    conversaciones_compartidas = (
        _conversaciones_compartidas(request.user)
    )

    conversacion = None

    if pk is not None:
        conversacion = _conversacion_visible(
            request.user,
            pk,
        )

    es_propietario = (
        conversacion is None
        or conversacion.user_id == request.user.pk
    )

    if (
        request.method == "POST"
        and not es_propietario
    ):
        raise PermissionDenied(
            "Las conversaciones compartidas "
            "son de solo lectura."
        )

    form = PreguntaIAForm(
        request.POST or None,
        request.FILES or None,
    )

    provider_status = obtener_estado_proveedor()

    if request.method == "POST" and form.is_valid():
        pregunta = form.cleaned_data[
            "pregunta"
        ].strip()
        validated_attachments = form.cleaned_data.get(
            "validated_attachments", []
        )

        try:
            committed_files = []
            try:
                with transaction.atomic():
                    if conversacion is None:
                        conversacion = (
                            ConversacionIA.objects.create(
                                user=request.user,
                                team=None,
                                titulo=(
                                    (pregunta or "Archivos adjuntos")[:157]
                                    + (
                                        "..."
                                        if len(pregunta or "") > 157
                                        else ""
                                    )
                                ),
                            )
                        )

                    mensaje_usuario = (
                        MensajeIA.objects.create(
                            conversacion=conversacion,
                            rol=MensajeIA.Rol.USUARIO,
                            contenido=pregunta,
                        )
                    )

                    conversacion.save(
                        update_fields=["updated_at"]
                    )

                    created_attachments = create_attachments(
                        conversation=conversacion,
                        message=mensaje_usuario,
                        owner=request.user,
                        validated_attachments=validated_attachments,
                    )
                    committed_files = [
                        attachment.file.name for attachment in created_attachments
                    ]
            except Exception:
                for storage_name in committed_files:
                    try:
                        private_ia_storage.delete(storage_name)
                    except Exception:
                        pass
                raise

            if validated_attachments:
                with transaction.atomic():
                    processing = ProcesamientoMensajeIA.objects.create(
                        message=mensaje_usuario,
                    )
                    transaction.on_commit(
                        lambda processing_id=processing.pk, task_key=str(processing.task_key):
                        process_document_message.delay(processing_id, task_key)
                    )
                messages.info(
                    request,
                    "Los archivos se están procesando. La respuesta aparecerá al finalizar.",
                )
                return redirect("intasa_ia:detalle", pk=conversacion.pk)

            if pregunta:
                resultado = generar_respuesta_segura(
                    pregunta=pregunta,
                    user=request.user,
                    team=None,
                    conversacion=conversacion,
                )

        except IAProviderError as exc:
            error_text = _mensaje_error_proveedor(
                exc.code
            )
            with transaction.atomic():
                MensajeIA.objects.create(
                    conversacion=conversacion,
                    rol=MensajeIA.Rol.ASISTENTE,
                    contenido=error_text,
                    proveedor="openai-error",
                    modelo=provider_status.get(
                        "model",
                        "",
                    ),
                    request_id=exc.request_id,
                    metadata={
                        "external_call": True,
                        "read_only": True,
                        "store": False,
                        "error_code": exc.code,
                        "http_status": exc.http_status,
                    },
                )

                conversacion.save(
                    update_fields=["updated_at"]
                )

            messages.error(
                request,
                error_text,
            )

            return redirect(
                "intasa_ia:detalle",
                pk=conversacion.pk,
            )

        else:
            with transaction.atomic():
                MensajeIA.objects.create(
                    conversacion=conversacion,
                    rol=MensajeIA.Rol.ASISTENTE,
                    contenido=resultado["contenido"],
                    proveedor=resultado["proveedor"],
                    modelo=resultado["modelo"],
                    request_id=resultado["request_id"],
                    tokens_entrada=resultado[
                        "tokens_entrada"
                    ],
                    tokens_salida=resultado[
                        "tokens_salida"
                    ],
                    metadata=resultado["metadata"],
                )

                conversacion.save(
                    update_fields=["updated_at"]
                )

                registrar_actividad(
                    modulo="INTASA_IA",
                    accion="CONSULTA",
                    actor=request.user,
                    team=None,
                    objeto=conversacion,
                    descripcion=(
                        "Consulta privada realizada "
                        "en INTASA IA."
                    ),
                    url=reverse(
                        "intasa_ia:detalle",
                        args=[conversacion.pk],
                    ),
                    visibilidad=(
                        ActividadPlataforma
                        .Visibilidad
                        .ACTOR
                    ),
                    metadata={
                        "mensaje_id": mensaje_usuario.pk,
                        "longitud": len(pregunta),
                        "external_call": (
                            resultado["metadata"].get(
                                "external_call",
                                False,
                            )
                        ),
                        "modelo": resultado["modelo"],
                        "web_search_used": bool(
                            resultado["metadata"].get(
                                "web_search_used",
                                False,
                            )
                        ),
                        "web_citation_count": len(
                            resultado["metadata"].get(
                                "web_citations",
                                [],
                            )
                        ),
                    },
                    visible_en_dashboard=False,
                )

            return redirect(
                "intasa_ia:detalle",
                pk=conversacion.pk,
            )

    share_form = None
    shared_accesses = []

    if (
        conversacion is not None
        and es_propietario
    ):
        share_form = CompartirConversacionForm(
            owner=request.user,
            conversation=conversacion,
        )

        shared_accesses = (
            conversacion.accesos_compartidos
            .select_related("user", "shared_by")
            .all()
        )

    return render(
        request,
        "intasa_ia/inicio.html",
        {
            "form": form,
            "share_form": share_form,
            "shared_accesses": shared_accesses,
            "conversacion": conversacion,
            "es_propietario": es_propietario,
            "conversaciones_propias": (
                conversaciones_propias[:30]
            ),
            "conversaciones_compartidas": (
                conversaciones_compartidas[:30]
            ),
            "modo_seguro": (
                not provider_status["enabled"]
            ),
            "proveedor_activo": (
                provider_status["enabled"]
            ),
            "modelo_activo": (
                provider_status["model"]
            ),
            "sugerencias_actuales": (
                SUGERENCIAS_ACTUALES
            ),
            "sugerencias_futuras": (
                SUGERENCIAS_FUTURAS
            ),
        },
    )


@login_required
@permission_required(
    "intasa_ia.use_intasa_ia",
    raise_exception=True,
)
@require_POST
def compartir(request, pk):
    conversacion = get_object_or_404(
        ConversacionIA,
        pk=pk,
        user=request.user,
    )

    form = CompartirConversacionForm(
        owner=request.user,
        conversation=conversacion,
        data=request.POST,
    )

    if not form.is_valid():
        messages.error(
            request,
            "Selecciona un usuario válido.",
        )

        return redirect(
            "intasa_ia:detalle",
            pk=conversacion.pk,
        )

    recipient = form.cleaned_data["usuario"]

    acceso, created = (
        AccesoConversacionIA.objects.get_or_create(
            conversacion=conversacion,
            user=recipient,
            defaults={
                "shared_by": request.user,
            },
        )
    )

    if created:
        messages.success(
            request,
            (
                "La conversación se ha compartido "
                f"con {recipient.get_full_name() or recipient.username}."
            ),
        )

        registrar_actividad(
            modulo="INTASA_IA",
            accion="COMPARTIR_CONVERSACION",
            actor=request.user,
            team=None,
            objeto=conversacion,
            descripcion=(
                "Conversación INTASA IA compartida "
                "en modo lectura."
            ),
            url=reverse(
                "intasa_ia:detalle",
                args=[conversacion.pk],
            ),
            visibilidad=(
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
            metadata={
                "recipient_user_id": recipient.pk,
                "read_only": True,
            },
            visible_en_dashboard=False,
        )
    else:
        messages.info(
            request,
            "La conversación ya estaba compartida.",
        )

    return redirect(
        "intasa_ia:detalle",
        pk=conversacion.pk,
    )


@login_required
@permission_required(
    "intasa_ia.use_intasa_ia",
    raise_exception=True,
)
@require_POST
def retirar_compartido(request, pk, user_id):
    conversacion = get_object_or_404(
        ConversacionIA,
        pk=pk,
        user=request.user,
    )

    deleted, _detail = (
        AccesoConversacionIA.objects
        .filter(
            conversacion=conversacion,
            user_id=user_id,
        )
        .delete()
    )

    if deleted:
        messages.success(
            request,
            "El acceso compartido ha sido retirado.",
        )
    else:
        messages.info(
            request,
            "El usuario ya no tenía acceso.",
        )

    return redirect(
        "intasa_ia:detalle",
        pk=conversacion.pk,
    )


@login_required
@permission_required(
    "intasa_ia.use_intasa_ia",
    raise_exception=True,
)
@require_POST
def eliminar_conversacion(request, pk):
    physical_delete_failures = []
    with transaction.atomic():
        conversacion = get_object_or_404(
            ConversacionIA.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )

        conversation_id = conversacion.pk
        message_count = conversacion.mensajes.count()
        shared_access_count = (
            conversacion.accesos_compartidos.count()
        )
        attachment_refs = list(
            conversacion.adjuntos.values_list("id", "file")
        )
        object_type = (
            ConversacionIA._meta.label_lower
        )

        (
            ActividadPlataforma.objects
            .filter(
                tipo_objeto=object_type,
                objeto_id=conversation_id,
            )
            .update(objeto_repr="")
        )

        conversacion.delete()

        schedule_physical_delete(
            attachment_refs,
            failure_bucket=physical_delete_failures,
        )

        registrar_actividad(
            modulo="INTASA_IA",
            accion="ELIMINAR",
            actor=request.user,
            team=None,
            objeto=None,
            tipo_objeto=object_type,
            objeto_id=conversation_id,
            objeto_repr="",
            descripcion=(
                "Conversación privada de INTASA IA "
                "eliminada por su propietario."
            ),
            url=reverse("intasa_ia:inicio"),
            visibilidad=(
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
            metadata={
                "conversation_id_deleted": (
                    conversation_id
                ),
                "message_count_deleted": (
                    message_count
                ),
                "shared_access_count_deleted": (
                    shared_access_count
                ),
                "permanent_delete": True,
                **(
                    {"attachment_count_deleted": len(attachment_refs)}
                    if attachment_refs else {}
                ),
            },
            visible_en_dashboard=False,
            diferir_hasta_commit=False,
        )

    if physical_delete_failures:
        messages.error(
            request,
            "La conversación se eliminó, pero algunos archivos quedan pendientes de purga.",
        )
    else:
        messages.success(
            request,
            "La conversación se ha eliminado definitivamente.",
        )

    return redirect("intasa_ia:inicio")


@login_required
@permission_required("intasa_ia.use_intasa_ia", raise_exception=True)
@require_GET
def descargar_adjunto(request, attachment_id):
    attachment = get_object_or_404(
        AdjuntoIA.objects.select_related("conversation").exclude(
            status=AdjuntoIA.Estado.DELETED
        ),
        Q(conversation__user=request.user)
        | Q(conversation__accesos_compartidos__user=request.user),
        pk=attachment_id,
    )
    try:
        stream = attachment.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404()

    registrar_actividad(
        modulo="INTASA_IA",
        accion="DESCARGAR_ADJUNTO",
        actor=request.user,
        team=None,
        objeto=attachment.conversation,
        descripcion="Descarga autorizada de adjunto INTASA IA.",
        url=reverse("intasa_ia:detalle", args=[attachment.conversation_id]),
        visibilidad=ActividadPlataforma.Visibilidad.ACTOR,
        metadata={"attachment_id": str(attachment.pk)},
        visible_en_dashboard=False,
    )
    response = FileResponse(stream, content_type=attachment.detected_mime)
    response["Content-Disposition"] = content_disposition_header(
        True, attachment.safe_display_name
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@login_required
@permission_required("intasa_ia.use_intasa_ia", raise_exception=True)
@require_GET
def estado_procesamiento(request, pk, message_id):
    conversation = get_object_or_404(
        ConversacionIA.objects.filter(
            Q(user=request.user) | Q(accesos_compartidos__user=request.user)
        ).distinct(), pk=pk,
    )
    processing = get_object_or_404(
        ProcesamientoMensajeIA.objects.select_related("assistant_message"),
        message_id=message_id, message__conversacion=conversation,
    )
    attachments = list(AdjuntoIA.objects.filter(message_id=message_id).values(
        "id", "status", "safe_display_name", "error_code"
    ))
    for attachment in attachments:
        attachment["id"] = str(attachment["id"])
        if attachment["status"] != AdjuntoIA.Estado.FAILED:
            attachment["error_code"] = ""
    return JsonResponse({
        "status": processing.status,
        "terminal": processing.status in {
            ProcesamientoMensajeIA.Estado.COMPLETED,
            ProcesamientoMensajeIA.Estado.FAILED,
        },
        "assistant_message_id": processing.assistant_message_id,
        "attachments": attachments,
    })


@login_required
@permission_required("intasa_ia.use_intasa_ia", raise_exception=True)
@require_POST
def reintentar_procesamiento(request, pk, message_id):
    conversation = get_object_or_404(ConversacionIA, pk=pk, user=request.user)
    with transaction.atomic():
        processing = get_object_or_404(
            ProcesamientoMensajeIA.objects.select_for_update(),
            message_id=message_id, message__conversacion=conversation,
            status=ProcesamientoMensajeIA.Estado.FAILED,
        )
        if processing.attempts >= 2:
            messages.error(request, "Se alcanzó el máximo de reintentos técnicos.")
            return redirect("intasa_ia:detalle", pk=pk)
        processing.status = ProcesamientoMensajeIA.Estado.QUEUED
        processing.error_code = ""
        processing.save(update_fields=("status", "error_code", "updated_at"))
        AdjuntoIA.objects.filter(
            message_id=message_id, status=AdjuntoIA.Estado.FAILED
        ).update(status=AdjuntoIA.Estado.UPLOADED, error_code="")
        transaction.on_commit(
            lambda: process_document_message.delay(processing.pk, str(processing.task_key))
        )
    messages.info(request, "Reintento de procesamiento encolado.")
    return redirect("intasa_ia:detalle", pk=pk)
