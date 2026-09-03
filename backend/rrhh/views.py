from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EmpleadoForm
from .models import Empleado, GrupoTrabajo


@login_required
def empleados_list(request):
    user_teams = request.user.teams.all()

    qs = (
        Empleado.objects
        .select_related("team", "user")
        .prefetch_related("grupos_trabajo")
        .filter(team__in=user_teams)
        .order_by("team__name", "nombre_completo")
    )

    team_id = request.GET.get("team")
    area = request.GET.get("area")
    situacion = request.GET.get("situacion")
    grupo_id = request.GET.get("grupo")
    q = (request.GET.get("q") or "").strip()

    if team_id:
        qs = qs.filter(team_id=team_id)

    if area:
        qs = qs.filter(area_principal=area)

    if situacion:
        qs = qs.filter(situacion=situacion)

    if grupo_id:
        qs = qs.filter(grupos_trabajo__id=grupo_id)

    if q:
        qs = qs.filter(nombre_completo__icontains=q)

    context = {
        "empleados": qs.distinct(),
        "teams": user_teams.order_by("name"),
        "grupos": GrupoTrabajo.objects.filter(team__in=user_teams, activo=True).select_related("team").order_by("team__name", "tipo", "nombre"),
        "area_choices": Empleado.AreaPrincipal.choices,
        "situacion_choices": Empleado.Situacion.choices,
        "filtros": {
            "team": team_id or "",
            "area": area or "",
            "situacion": situacion or "",
            "grupo": grupo_id or "",
            "q": q,
        },
        "total_empleados": qs.distinct().count(),
    }
    return render(request, "rrhh/empleados_list.html", context)


@login_required
def empleado_detail(request, pk):
    user_teams = request.user.teams.all()

    empleado = get_object_or_404(
        Empleado.objects
        .select_related("team", "user")
        .prefetch_related("grupos_trabajo"),
        pk=pk,
        team__in=user_teams,
    )

    empleados_obra_legacy = (
        empleado.empleados_obra_legacy
        .select_related("team")
        .order_by("nombre")
    )

    recursos_reales_count = 0
    try:
        from planificacion_obra.models import TareaRecursoReal
        recursos_reales_count = TareaRecursoReal.objects.filter(
            empleado__rrhh_empleado=empleado
        ).count()
    except Exception:
        recursos_reales_count = 0

    context = {
        "empleado": empleado,
        "grupos": empleado.grupos_trabajo.all(),
        "empleados_obra_legacy": empleados_obra_legacy,
        "recursos_reales_count": recursos_reales_count,
    }
    return render(request, "rrhh/empleado_detail.html", context)


@login_required
def empleado_create(request):
    if request.method == "POST":
        form = EmpleadoForm(request.POST, request_user=request.user)
        if form.is_valid():
            empleado = form.save()
            messages.success(request, "Empleado creado correctamente.")
            return redirect("rrhh:empleado_detail", pk=empleado.pk)
    else:
        form = EmpleadoForm(request_user=request.user)

    return render(request, "rrhh/empleado_form.html", {
        "form": form,
        "modo": "crear",
        "titulo": "Nuevo empleado",
    })


@login_required
def empleado_edit(request, pk):
    empleado = get_object_or_404(
        Empleado,
        pk=pk,
        team__in=request.user.teams.all(),
    )

    if request.method == "POST":
        form = EmpleadoForm(request.POST, instance=empleado, request_user=request.user)
        if form.is_valid():
            empleado = form.save()
            messages.success(request, "Empleado actualizado correctamente.")
            return redirect("rrhh:empleado_detail", pk=empleado.pk)
    else:
        form = EmpleadoForm(instance=empleado, request_user=request.user)

    return render(request, "rrhh/empleado_form.html", {
        "form": form,
        "modo": "editar",
        "titulo": f"Editar empleado · {empleado.nombre_completo}",
        "empleado": empleado,
    })

# ============================================================================
# RRHH_SELECCION_PERSONAL_V1
# ============================================================================

from urllib.parse import quote

from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils import timezone

from actividad.models import ActividadPlataforma
from actividad.services import registrar_actividad
from usuarios.models import Team

from .forms import (
    CandidaturaForm,
    CandidaturaSeguimientoForm,
    ProcesoSeleccionForm,
)
from .models import (
    Candidatura,
    CandidaturaSeguimiento,
    ProcesoSeleccion,
)


RECRUITMENT_PERMISSION = "rrhh.access_recruitment"


def _recruitment_teams(user):
    if user.is_superuser:
        return Team.objects.all()
    return user.teams.all()


def _recruitment_active_team_id(request, teams):
    explicit = request.GET.get("team")
    if explicit is not None:
        if explicit == "":
            return None
        if explicit.isdigit() and teams.filter(pk=int(explicit)).exists():
            return int(explicit)
        return None

    session_value = request.session.get("active_team_id")
    if str(session_value).isdigit():
        team_id = int(session_value)
        if teams.filter(pk=team_id).exists():
            return team_id
    return None


def _recruitment_activity(actor, action, obj, description, metadata=None):
    registrar_actividad(
        modulo="RRHH",
        accion=action,
        actor=actor,
        objeto=obj,
        descripcion=description,
        url=(
            reverse("rrhh:candidatura_detail", kwargs={"pk": obj.pk})
            if isinstance(obj, Candidatura)
            else ""
        ),
        visibilidad=ActividadPlataforma.Visibilidad.EQUIPO,
        metadata=metadata or {},
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def seleccion_personal_list(request):
    teams = _recruitment_teams(request.user)
    selected_team_id = _recruitment_active_team_id(request, teams)

    qs = (
        Candidatura.objects
        .select_related(
            "proceso",
            "proceso__team",
            "candidato",
            "responsable",
            "cv_archivo",
        )
        .filter(proceso__team__in=teams)
    )

    if selected_team_id:
        qs = qs.filter(proceso__team_id=selected_team_id)

    q = (request.GET.get("q") or "").strip()
    proceso_id = request.GET.get("proceso") or ""
    estado = request.GET.get("estado") or ""
    origen = request.GET.get("origen") or ""
    puntuacion = request.GET.get("puntuacion") or ""

    if q:
        qs = qs.filter(
            Q(candidato__nombre_completo__icontains=q)
            | Q(candidato__email__icontains=q)
            | Q(candidato__telefono__icontains=q)
            | Q(candidato__ciudad__icontains=q)
            | Q(candidato__perfil_profesional__icontains=q)
            | Q(proceso__titulo__icontains=q)
            | Q(observaciones_revision__icontains=q)
            | Q(observaciones_entrevista__icontains=q)
        )

    if proceso_id.isdigit():
        qs = qs.filter(proceso_id=int(proceso_id))
    if estado in dict(Candidatura.Estado.choices):
        qs = qs.filter(estado=estado)
    if origen in dict(Candidatura.Origen.choices):
        qs = qs.filter(origen=origen)
    if puntuacion.isdigit() and 1 <= int(puntuacion) <= 5:
        qs = qs.filter(puntuacion=int(puntuacion))

    qs = qs.order_by("-fecha_solicitud", "-id")
    # RRHH_CV_FAST_LOAD_DUPLICATE_DELETE_V1
    page_obj = Paginator(qs, 100).get_page(request.GET.get("page"))

    procesos = (
        ProcesoSeleccion.objects
        .filter(team__in=teams)
        .select_related("team", "responsable")
        .annotate(total_candidaturas=Count("candidaturas"))
        .order_by("-fecha_apertura", "team__name", "titulo")
    )
    if selected_team_id:
        procesos = procesos.filter(team_id=selected_team_id)

    base_qs = Candidatura.objects.filter(proceso__team__in=teams)
    if selected_team_id:
        base_qs = base_qs.filter(proceso__team_id=selected_team_id)

    return render(
        request,
        "rrhh/seleccion_list.html",
        {
            "page_obj": page_obj,
            "candidaturas": page_obj.object_list,
            "procesos": procesos,
            "teams": teams.order_by("name"),
            "selected_team_id": str(selected_team_id or ""),
            "estado_choices": Candidatura.Estado.choices,
            "origen_choices": Candidatura.Origen.choices,
            "filtros": {
                "q": q,
                "proceso": proceso_id,
                "estado": estado,
                "origen": origen,
                "puntuacion": puntuacion,
            },
            "metricas": {
                "total": base_qs.count(),
                "preseleccionados": base_qs.filter(
                    estado=Candidatura.Estado.PRESELECCIONADO
                ).count(),
                "entrevistas": base_qs.filter(
                    estado__in=[
                        Candidatura.Estado.ENTREVISTA_PROGRAMADA,
                        Candidatura.Estado.ENTREVISTADO,
                    ]
                ).count(),
                "seleccionados": base_qs.filter(
                    estado__in=[
                        Candidatura.Estado.SELECCIONADO,
                        Candidatura.Estado.CONTRATADO,
                    ]
                ).count(),
            },
        },
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def proceso_seleccion_create(request):
    if request.method == "POST":
        form = ProcesoSeleccionForm(request.POST, request_user=request.user)
        if form.is_valid():
            proceso = form.save(commit=False)
            proceso.creado_por = request.user
            proceso.modificado_por = request.user
            proceso.save()
            registrar_actividad(
                modulo="RRHH",
                accion="CREAR_PROCESO_SELECCION",
                actor=request.user,
                objeto=proceso,
                descripcion=f"Creó el proceso de selección {proceso.titulo}.",
                url=reverse(
                    "rrhh:proceso_seleccion_detail",
                    kwargs={"pk": proceso.pk},
                ),
                visibilidad=ActividadPlataforma.Visibilidad.EQUIPO,
            )
            messages.success(request, "Proceso de selección creado correctamente.")
            return redirect("rrhh:proceso_seleccion_detail", pk=proceso.pk)
    else:
        initial = {}
        active_team_id = request.session.get("active_team_id")
        if str(active_team_id).isdigit():
            initial["team"] = active_team_id
        form = ProcesoSeleccionForm(initial=initial, request_user=request.user)

    return render(
        request,
        "rrhh/proceso_seleccion_form.html",
        {"form": form, "titulo": "Nuevo proceso de selección"},
    )


# RRHH_FILTERED_PRINT_V1
@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def seleccion_personal_print(request):
    """
    Vista imprimible de todas las candidaturas que coinciden con los
    filtros activos. No pagina, no escribe datos y mantiene el ámbito
    de empresas permitido al usuario.
    """
    from django.db.models import Q
    from django.shortcuts import render
    from django.utils import timezone

    teams = _recruitment_teams(request.user)
    selected_team_id = _recruitment_active_team_id(
        request,
        teams,
    )

    qs = (
        Candidatura.objects
        .select_related(
            "proceso",
            "proceso__team",
            "candidato",
            "responsable",
        )
        .filter(proceso__team__in=teams)
    )

    if selected_team_id:
        qs = qs.filter(proceso__team_id=selected_team_id)

    q = (request.GET.get("q") or "").strip()
    proceso_id = request.GET.get("proceso") or ""
    estado = request.GET.get("estado") or ""
    origen = request.GET.get("origen") or ""
    puntuacion = request.GET.get("puntuacion") or ""

    if q:
        qs = qs.filter(
            Q(candidato__nombre_completo__icontains=q)
            | Q(candidato__email__icontains=q)
            | Q(candidato__telefono__icontains=q)
            | Q(candidato__ciudad__icontains=q)
            | Q(candidato__perfil_profesional__icontains=q)
            | Q(proceso__titulo__icontains=q)
            | Q(observaciones_revision__icontains=q)
            | Q(observaciones_entrevista__icontains=q)
        )

    selected_process = None

    if proceso_id.isdigit():
        selected_process = (
            ProcesoSeleccion.objects
            .filter(
                pk=int(proceso_id),
                team__in=teams,
            )
            .select_related("team")
            .first()
        )
        if selected_process is not None:
            qs = qs.filter(proceso_id=selected_process.pk)

    estado_choices = dict(Candidatura.Estado.choices)
    origen_choices = dict(Candidatura.Origen.choices)

    if estado in estado_choices:
        qs = qs.filter(estado=estado)

    if origen in origen_choices:
        qs = qs.filter(origen=origen)

    valid_score = (
        puntuacion.isdigit()
        and 1 <= int(puntuacion) <= 5
    )
    if valid_score:
        qs = qs.filter(puntuacion=int(puntuacion))

    qs = qs.order_by("-fecha_solicitud", "-id")

    selected_team = None
    if selected_team_id:
        selected_team = teams.filter(
            pk=selected_team_id
        ).first()

    distinct_processes = (
        qs.values("proceso_id")
        .distinct()
        .count()
    )

    return render(
        request,
        "rrhh/seleccion_print.html",
        {
            "candidaturas": qs,
            "total": qs.count(),
            "generated_at": timezone.localtime(),
            "show_process_in_rows": distinct_processes > 1,
            "filter_labels": {
                "q": q or "Sin búsqueda",
                "team": (
                    selected_team.name
                    if selected_team is not None
                    else "Todas las permitidas"
                ),
                "proceso": (
                    selected_process.titulo
                    if selected_process is not None
                    else "Todos"
                ),
                "estado": estado_choices.get(estado, "Todos"),
                "origen": origen_choices.get(origen, "Todos"),
                "puntuacion": (
                    f"{int(puntuacion)}/5"
                    if valid_score
                    else "Todas"
                ),
            },
        },
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def proceso_seleccion_detail(request, pk):
    teams = _recruitment_teams(request.user)
    proceso = get_object_or_404(
        ProcesoSeleccion.objects.select_related("team", "responsable", "creado_por"),
        pk=pk,
        team__in=teams,
    )
    candidaturas = (
        proceso.candidaturas
        .select_related("candidato", "responsable", "cv_archivo")
        .order_by("-fecha_solicitud", "-id")
    )
    return render(
        request,
        "rrhh/proceso_seleccion_detail.html",
        {"proceso": proceso, "candidaturas": candidaturas},
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def proceso_seleccion_edit(request, pk):
    teams = _recruitment_teams(request.user)
    proceso = get_object_or_404(
        ProcesoSeleccion,
        pk=pk,
        team__in=teams,
    )
    if request.method == "POST":
        form = ProcesoSeleccionForm(
            request.POST,
            instance=proceso,
            request_user=request.user,
        )
        if form.is_valid():
            proceso = form.save(commit=False)
            proceso.modificado_por = request.user
            proceso.save()
            messages.success(request, "Proceso de selección actualizado.")
            return redirect("rrhh:proceso_seleccion_detail", pk=proceso.pk)
    else:
        form = ProcesoSeleccionForm(
            instance=proceso,
            request_user=request.user,
        )
    return render(
        request,
        "rrhh/proceso_seleccion_form.html",
        {
            "form": form,
            "titulo": f"Editar proceso · {proceso.titulo}",
            "proceso": proceso,
        },
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_create(request):
    initial = {}
    proceso_id = request.GET.get("proceso")
    if proceso_id and proceso_id.isdigit():
        proceso_inicial = (
            ProcesoSeleccion.objects
            .filter(
                pk=int(proceso_id),
                team__in=_recruitment_teams(request.user),
            )
            .select_related("responsable")
            .first()
        )
        if proceso_inicial:
            initial["proceso"] = proceso_inicial.pk
            initial["responsable"] = proceso_inicial.responsable_id

    if request.method == "POST":
        form = CandidaturaForm(
            request.POST,
            request.FILES,
            request_user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                candidatura = form.save()
                CandidaturaSeguimiento.objects.create(
                    candidatura=candidatura,
                    tipo=CandidaturaSeguimiento.Tipo.ALTA,
                    fecha=timezone.now(),
                    completado=True,
                    notas="Candidatura registrada en Portal INTASA.",
                    estado_nuevo=candidatura.estado,
                    usuario=request.user,
                )
                _recruitment_activity(
                    request.user,
                    "CREAR_CANDIDATURA",
                    candidatura,
                    (
                        f"Registró la candidatura de "
                        f"{candidatura.candidato.nombre_completo} "
                        f"para {candidatura.proceso.titulo}."
                    ),
                    {
                        "estado": candidatura.estado,
                        "puntuacion": candidatura.puntuacion,
                    },
                )
            messages.success(request, "Candidatura creada correctamente.")
            return redirect("rrhh:candidatura_detail", pk=candidatura.pk)
    else:
        form = CandidaturaForm(initial=initial, request_user=request.user)

    return render(
        request,
        "rrhh/candidatura_form.html",
        {"form": form, "titulo": "Nueva candidatura"},
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_detail(request, pk):
    teams = _recruitment_teams(request.user)
    candidatura = get_object_or_404(
        Candidatura.objects
        .select_related(
            "proceso",
            "proceso__team",
            "candidato",
            "responsable",
            "cv_archivo",
            "creado_por",
            "modificado_por",
        )
        .prefetch_related("seguimientos__usuario"),
        pk=pk,
        proceso__team__in=teams,
    )
    return render(
        request,
        "rrhh/candidatura_detail.html",
        {
            "candidatura": candidatura,
            "seguimiento_form": CandidaturaSeguimientoForm(),
            "seguimientos": candidatura.seguimientos.all(),
        },
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_edit(request, pk):
    teams = _recruitment_teams(request.user)
    candidatura = get_object_or_404(
        Candidatura.objects.select_related("proceso", "candidato"),
        pk=pk,
        proceso__team__in=teams,
    )
    estado_anterior = candidatura.estado

    if request.method == "POST":
        form = CandidaturaForm(
            request.POST,
            request.FILES,
            instance=candidatura,
            request_user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                candidatura = form.save()
                if estado_anterior != candidatura.estado:
                    CandidaturaSeguimiento.objects.create(
                        candidatura=candidatura,
                        tipo=CandidaturaSeguimiento.Tipo.CAMBIO_ESTADO,
                        fecha=timezone.now(),
                        completado=True,
                        notas=(
                            f"Estado cambiado a "
                            f"{candidatura.get_estado_display()}."
                        ),
                        estado_anterior=estado_anterior,
                        estado_nuevo=candidatura.estado,
                        usuario=request.user,
                    )
                _recruitment_activity(
                    request.user,
                    "ACTUALIZAR_CANDIDATURA",
                    candidatura,
                    (
                        f"Actualizó la candidatura de "
                        f"{candidatura.candidato.nombre_completo}."
                    ),
                    {
                        "estado_anterior": estado_anterior,
                        "estado_nuevo": candidatura.estado,
                        "puntuacion": candidatura.puntuacion,
                    },
                )
            messages.success(request, "Candidatura actualizada correctamente.")
            return redirect("rrhh:candidatura_detail", pk=candidatura.pk)
    else:
        form = CandidaturaForm(
            instance=candidatura,
            request_user=request.user,
        )

    return render(
        request,
        "rrhh/candidatura_form.html",
        {
            "form": form,
            "titulo": (
                f"Editar candidatura · "
                f"{candidatura.candidato.nombre_completo}"
            ),
            "candidatura": candidatura,
        },
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_seguimiento_add(request, pk):
    teams = _recruitment_teams(request.user)
    candidatura = get_object_or_404(
        Candidatura.objects.select_related("proceso", "candidato"),
        pk=pk,
        proceso__team__in=teams,
    )

    if request.method != "POST":
        return redirect("rrhh:candidatura_detail", pk=candidatura.pk)

    form = CandidaturaSeguimientoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los datos del seguimiento.")
        return redirect("rrhh:candidatura_detail", pk=candidatura.pk)

    with transaction.atomic():
        seguimiento = form.save(commit=False)
        seguimiento.candidatura = candidatura
        seguimiento.usuario = request.user
        seguimiento.save()

        update_fields = []
        if (
            seguimiento.tipo == CandidaturaSeguimiento.Tipo.LLAMADA
            and not seguimiento.completado
        ):
            candidatura.fecha_proximo_contacto = seguimiento.fecha
            update_fields.append("fecha_proximo_contacto")

        if (
            seguimiento.tipo == CandidaturaSeguimiento.Tipo.ENTREVISTA
            and not seguimiento.completado
        ):
            candidatura.fecha_entrevista = seguimiento.fecha
            update_fields.append("fecha_entrevista")
            if candidatura.estado not in {
                Candidatura.Estado.SELECCIONADO,
                Candidatura.Estado.CONTRATADO,
                Candidatura.Estado.DESCARTADO,
            }:
                candidatura.estado = Candidatura.Estado.ENTREVISTA_PROGRAMADA
                update_fields.append("estado")

        if update_fields:
            candidatura.modificado_por = request.user
            update_fields.extend(["modificado_por", "actualizado_en"])
            candidatura.save(update_fields=list(dict.fromkeys(update_fields)))

        _recruitment_activity(
            request.user,
            "SEGUIMIENTO_CANDIDATURA",
            candidatura,
            (
                f"Registró {seguimiento.get_tipo_display().lower()} "
                f"para {candidatura.candidato.nombre_completo}."
            ),
            {
                "tipo": seguimiento.tipo,
                "fecha": seguimiento.fecha.isoformat(),
                "completado": seguimiento.completado,
            },
        )

    messages.success(request, "Seguimiento registrado.")
    return redirect("rrhh:candidatura_detail", pk=candidatura.pk)


def _content_disposition(filename):
    return f"inline; filename*=UTF-8''{quote(filename or 'curriculum.pdf')}"


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_cv(request, pk):
    teams = _recruitment_teams(request.user)
    candidatura = get_object_or_404(
        Candidatura.objects.select_related(
            "proceso",
            "proceso__team",
            "cv_archivo",
        ),
        pk=pk,
        proceso__team__in=teams,
    )

    if candidatura.cv_fichero:
        try:
            stream = candidatura.cv_fichero.open("rb")
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise Http404("El currículo no está disponible.") from exc
        response = FileResponse(stream, content_type="application/pdf")
        response["Content-Disposition"] = _content_disposition(
            candidatura.cv_nombre
        )
        return response

    if candidatura.cv_archivo_id:
        archivo = candidatura.cv_archivo
        try:
            from archivos.storage_providers import get_storage_provider
            provider = get_storage_provider(archivo.storage_provider)
            if not provider.exists(archivo):
                raise Http404("El currículo vinculado no existe.")
            stream = provider.open(archivo, "rb")
        except Http404:
            raise
        except Exception as exc:
            raise Http404(
                "El currículo vinculado no está disponible."
            ) from exc

        response = FileResponse(
            stream,
            content_type=archivo.mimetype or "application/pdf",
        )
        response["Content-Disposition"] = _content_disposition(
            archivo.nombre_original
        )
        return response

    raise Http404("La candidatura no tiene currículo.")

# ============================================================================
# RRHH_CV_OCR_V1
# ============================================================================

@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_desde_cv(request, proceso_pk):
    import re
    import uuid

    from django.contrib import messages
    from django.core import signing
    from django.core.exceptions import ValidationError
    from django.core.files import File
    from django.shortcuts import get_object_or_404, redirect, render

    from .services.cv_duplicates import (
        find_duplicate_applications,
        resolve_candidate_for_team,
        sha256_path,
    )
    from .services.cv_ocr import analyze_cv_pdf, pending_directory

    token_salt = "rrhh-cv-ocr-v1"
    teams = _recruitment_teams(request.user)
    proceso = get_object_or_404(
        ProcesoSeleccion.objects.select_related("team", "responsable"),
        pk=proceso_pk,
        team__in=teams,
    )

    def render_page(
        *,
        result=None,
        token="",
        initial=None,
        form_errors=None,
        duplicate_matches=None,
        allow_duplicate=False,
    ):
        duplicate_matches = duplicate_matches or []
        return render(
            request,
            "rrhh/candidatura_desde_cv.html",
            {
                "proceso": proceso,
                "result": result,
                "token": token,
                "initial": initial or {},
                "form_errors": form_errors,
                "duplicate_matches": duplicate_matches,
                "strong_duplicate_matches": [
                    item
                    for item in duplicate_matches
                    if item.get("strong")
                ],
                "hard_duplicate_matches": [
                    item
                    for item in duplicate_matches
                    if item.get("hard")
                ],
                "overridable_duplicate_matches": [
                    item
                    for item in duplicate_matches
                    if item.get("strong")
                    and not item.get("hard")
                ],
                "allow_duplicate": allow_duplicate,
                "origen_choices": Candidatura.Origen.choices,
                "today": timezone.localdate().isoformat(),
            },
        )

    if request.method != "POST":
        return render_page()

    action = request.POST.get("_action") or "extract"

    if action == "extract":
        uploaded = request.FILES.get("cv_pdf")
        if not uploaded:
            messages.error(request, "Selecciona un currículo PDF.")
            return render_page()

        original_name = uploaded.name or "curriculum.pdf"
        content_type = (
            getattr(uploaded, "content_type", "") or ""
        ).lower()

        if (
            not original_name.lower().endswith(".pdf")
            and content_type != "application/pdf"
        ):
            messages.error(
                request,
                "El currículo debe ser un archivo PDF.",
            )
            return render_page()

        if uploaded.size > 15 * 1024 * 1024:
            messages.error(
                request,
                "El currículo no puede superar 15 MB.",
            )
            return render_page()

        header = uploaded.read(5)
        uploaded.seek(0)
        if header != b"%PDF-":
            messages.error(
                request,
                "El archivo seleccionado no parece un PDF válido.",
            )
            return render_page()

        pending_name = f"{uuid.uuid4().hex}.pdf"
        pending_path = pending_directory() / pending_name

        try:
            with pending_path.open("wb") as destination:
                for chunk in uploaded.chunks():
                    destination.write(chunk)

            cv_sha256 = sha256_path(pending_path)
            result = analyze_cv_pdf(pending_path, original_name)
        except ValidationError as exc:
            pending_path.unlink(missing_ok=True)
            messages.error(
                request,
                (
                    exc.messages[0]
                    if getattr(exc, "messages", None)
                    else str(exc)
                ),
            )
            return render_page()
        except Exception:
            pending_path.unlink(missing_ok=True)
            messages.error(
                request,
                "No se pudo analizar el currículo. "
                "El PDF no fue guardado.",
            )
            return render_page()

        token = signing.dumps(
            {
                "user_id": request.user.pk,
                "proceso_id": proceso.pk,
                "pending_name": pending_name,
                "original_name": original_name,
                "method": result.get("method") or "",
                "ocr_used": bool(result.get("ocr_used")),
                "cv_sha256": cv_sha256,
            },
            salt=token_salt,
            compress=True,
        )

        initial = dict(result["fields"])
        initial.update(
            {
                "origen": Candidatura.Origen.OTRO,
                "fecha_solicitud": (
                    timezone.localdate().isoformat()
                ),
                "puntuacion": "",
            }
        )

        duplicate_matches = find_duplicate_applications(
            proceso,
            cv_sha256=cv_sha256,
            email=initial.get("email", ""),
            phone=initial.get("telefono", ""),
            name=initial.get("nombre_completo", ""),
            filename=original_name,
        )

        return render_page(
            result=result,
            token=token,
            initial=initial,
            duplicate_matches=duplicate_matches,
        )

    if action != "confirm":
        messages.error(request, "Acción no reconocida.")
        return redirect(
            "rrhh:candidatura_desde_cv",
            proceso_pk=proceso.pk,
        )

    token = request.POST.get("token") or ""
    try:
        payload = signing.loads(
            token,
            salt=token_salt,
            max_age=3600,
        )
    except signing.BadSignature:
        messages.error(
            request,
            "La previsualización ha caducado. "
            "Vuelve a analizar el currículo.",
        )
        return redirect(
            "rrhh:candidatura_desde_cv",
            proceso_pk=proceso.pk,
        )

    if (
        payload.get("user_id") != request.user.pk
        or payload.get("proceso_id") != proceso.pk
    ):
        raise Http404(
            "La previsualización no corresponde a este proceso."
        )

    pending_name = str(payload.get("pending_name") or "")
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", pending_name):
        raise Http404(
            "Referencia temporal de currículo no válida."
        )

    pending_path = pending_directory() / pending_name
    if not pending_path.is_file():
        messages.error(
            request,
            "El currículo temporal ya no está disponible. "
            "Vuelve a analizarlo.",
        )
        return redirect(
            "rrhh:candidatura_desde_cv",
            proceso_pk=proceso.pk,
        )

    initial = {
        key: request.POST.get(key, "")
        for key in (
            "nombre_completo",
            "telefono",
            "email",
            "ciudad",
            "perfil_profesional",
            "linkedin_url",
            "observaciones_candidato",
            "origen",
            "fecha_solicitud",
            "puntuacion",
            "observaciones_revision",
        )
    }

    original_name = str(
        payload.get("original_name") or "curriculum.pdf"
    )
    cv_sha256 = str(payload.get("cv_sha256") or "")

    duplicate_matches = find_duplicate_applications(
        proceso,
        cv_sha256=cv_sha256,
        email=initial.get("email", ""),
        phone=initial.get("telefono", ""),
        name=initial.get("nombre_completo", ""),
        filename=original_name,
    )
    strong_duplicates = [
        item
        for item in duplicate_matches
        if item.get("strong")
    ]
    hard_duplicates = [
        item
        for item in duplicate_matches
        if item.get("hard")
    ]
    allow_duplicate = (
        request.POST.get("allow_duplicate") == "1"
    )

    result = {
        "method": payload.get("method") or "",
        "ocr_used": bool(payload.get("ocr_used")),
        "missing": [],
        "text_preview": "",
        "text_length": 0,
    }

    if hard_duplicates or (
        strong_duplicates and not allow_duplicate
    ):
        messages.warning(
            request,
            (
                "Este PDF ya está cargado en el proceso y no "
                "puede repetirse."
                if hard_duplicates
                else (
                    "Se ha detectado una posible candidatura "
                    "repetida. Comprueba los registros "
                    "existentes antes de continuar."
                )
            ),
        )
        return render_page(
            result=result,
            token=token,
            initial=initial,
            duplicate_matches=duplicate_matches,
            allow_duplicate=False,
        )

    data = request.POST.copy()
    data["proceso"] = str(proceso.pk)
    data["responsable"] = (
        str(proceso.responsable_id)
        if proceso.responsable_id
        else ""
    )
    data["estado"] = Candidatura.Estado.RECIBIDO
    data["cv_archivo"] = ""

    candidate_instance = resolve_candidate_for_team(
        proceso.team,
        email=initial.get("email", ""),
        phone=initial.get("telefono", ""),
    )

    if (
        candidate_instance
        and Candidatura.objects.filter(
            proceso=proceso,
            candidato=candidate_instance,
        ).exists()
    ):
        # La coincidencia ya pertenece a este proceso. Si el usuario
        # fuerza el alta, debe crearse un candidato separado para no
        # vulnerar la restricción proceso+candidato.
        candidate_instance = None

    handle = pending_path.open("rb")
    django_file = File(handle, name=original_name)

    form = CandidaturaForm(
        data,
        {"cv_fichero": django_file},
        request_user=request.user,
        candidate_instance=candidate_instance,
    )

    if not form.is_valid():
        handle.close()
        messages.error(
            request,
            "Revisa los datos antes de confirmar.",
        )
        return render_page(
            result=result,
            token=token,
            initial=initial,
            form_errors=form.errors,
            duplicate_matches=duplicate_matches,
            allow_duplicate=allow_duplicate,
        )

    try:
        with transaction.atomic():
            candidatura = form.save()

            if (
                cv_sha256
                and candidatura.cv_sha256 != cv_sha256
            ):
                candidatura.cv_sha256 = cv_sha256
                candidatura.save(
                    update_fields=[
                        "cv_sha256",
                        "actualizado_en",
                    ]
                )

            CandidaturaSeguimiento.objects.create(
                candidatura=candidatura,
                tipo=CandidaturaSeguimiento.Tipo.ALTA,
                fecha=timezone.now(),
                completado=True,
                notas=(
                    "Candidatura creada desde currículo PDF "
                    "revisado."
                ),
                estado_nuevo=candidatura.estado,
                usuario=request.user,
            )
            _recruitment_activity(
                request.user,
                "CREAR_CANDIDATURA_CV_OCR",
                candidatura,
                (
                    f"Registró la candidatura de "
                    f"{candidatura.candidato.nombre_completo} "
                    f"desde currículo PDF para {proceso.titulo}."
                ),
                {
                    "estado": candidatura.estado,
                    "puntuacion": candidatura.puntuacion,
                    "metodo_lectura": (
                        payload.get("method") or ""
                    ),
                    "ocr_usado": bool(
                        payload.get("ocr_used")
                    ),
                    "responsable_id": (
                        candidatura.responsable_id
                    ),
                    "duplicado_forzado": bool(
                        strong_duplicates
                        and allow_duplicate
                    ),
                },
            )
    finally:
        handle.close()

    pending_path.unlink(missing_ok=True)

    after_save = (
        request.POST.get("after_save") or "next"
    )

    if after_save == "detail":
        messages.success(
            request,
            "Candidatura creada y currículo PDF "
            "guardado correctamente.",
        )
        return redirect(
            "rrhh:candidatura_detail",
            pk=candidatura.pk,
        )

    messages.success(
        request,
        "Candidatura creada correctamente. "
        "Puedes cargar otro currículo.",
    )
    return redirect(
        "rrhh:candidatura_desde_cv",
        proceso_pk=proceso.pk,
    )

# ============================================================================
# RRHH_CV_PDF_VIEWER_V1_2
# ============================================================================

from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
@xframe_options_sameorigin
@never_cache
def candidatura_cv_preview(request, proceso_pk):
    """
    Sirve únicamente el PDF temporal asociado a una previsualización OCR.

    Seguridad:
    - permiso RRHH;
    - ámbito de empresa;
    - token firmado y limitado a una hora;
    - token ligado al usuario y al proceso;
    - nombre temporal UUID estricto;
    - respuesta inline, privada y no cacheable.
    """
    import re

    from django.core import signing
    from django.http import FileResponse, Http404
    from django.shortcuts import get_object_or_404

    from .services.cv_ocr import pending_directory

    proceso = get_object_or_404(
        ProcesoSeleccion.objects.select_related("team"),
        pk=proceso_pk,
        team__in=_recruitment_teams(request.user),
    )

    token = request.GET.get("token") or ""

    try:
        payload = signing.loads(
            token,
            salt="rrhh-cv-ocr-v1",
            max_age=3600,
        )
    except signing.BadSignature as exc:
        raise Http404(
            "La previsualización del currículo no es válida o ha caducado."
        ) from exc

    if (
        payload.get("user_id") != request.user.pk
        or payload.get("proceso_id") != proceso.pk
    ):
        raise Http404(
            "La previsualización no corresponde a este usuario o proceso."
        )

    pending_name = str(payload.get("pending_name") or "")
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", pending_name):
        raise Http404("Referencia temporal de currículo no válida.")

    pending_path = pending_directory() / pending_name
    if not pending_path.is_file():
        raise Http404("El currículo temporal ya no está disponible.")

    try:
        stream = pending_path.open("rb")
    except (FileNotFoundError, OSError) as exc:
        raise Http404(
            "El currículo temporal ya no está disponible."
        ) from exc

    response = FileResponse(
        stream,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = _content_disposition(
        str(payload.get("original_name") or "curriculum.pdf")
    )
    response["Cache-Control"] = (
        "private, no-store, no-cache, must-revalidate, max-age=0"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response

# ============================================================================
# RRHH_CV_FAST_LOAD_DUPLICATE_DELETE_V1
# ============================================================================

@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_cv_remove(request, pk):
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect, render

    from .services.cv_duplicates import delete_stored_file

    candidatura = get_object_or_404(
        Candidatura.objects.select_related(
            "proceso",
            "proceso__team",
            "candidato",
            "cv_archivo",
        ),
        pk=pk,
        proceso__team__in=_recruitment_teams(request.user),
    )

    if request.method != "POST":
        return render(
            request,
            "rrhh/candidatura_confirm_action.html",
            {
                "candidatura": candidatura,
                "action_mode": "remove_cv",
            },
        )

    if not candidatura.cv_disponible:
        messages.info(
            request,
            "La candidatura ya no tiene currículo.",
        )
        return redirect(
            "rrhh:candidatura_detail",
            pk=candidatura.pk,
        )

    storage = (
        candidatura.cv_fichero.storage
        if candidatura.cv_fichero
        else None
    )
    stored_name = (
        candidatura.cv_fichero.name
        if candidatura.cv_fichero
        else ""
    )
    previous_name = candidatura.cv_nombre

    with transaction.atomic():
        candidatura.cv_fichero = ""
        candidatura.cv_archivo = None
        candidatura.cv_nombre_original = ""
        candidatura.cv_sha256 = ""
        candidatura.modificado_por = request.user
        candidatura.save(
            update_fields=[
                "cv_fichero",
                "cv_archivo",
                "cv_nombre_original",
                "cv_sha256",
                "modificado_por",
                "actualizado_en",
            ]
        )

        _recruitment_activity(
            request.user,
            "ELIMINAR_CV_CANDIDATURA",
            candidatura,
            (
                f"Quitó el currículo de la candidatura de "
                f"{candidatura.candidato.nombre_completo}."
            ),
            {
                "nombre_anterior": previous_name,
            },
        )

        if storage and stored_name:
            transaction.on_commit(
                lambda s=storage, n=stored_name: (
                    delete_stored_file(s, n)
                )
            )

    messages.success(
        request,
        "Currículo eliminado de la candidatura.",
    )
    return redirect(
        "rrhh:candidatura_detail",
        pk=candidatura.pk,
    )


@login_required
@permission_required(RECRUITMENT_PERMISSION, raise_exception=True)
def candidatura_delete(request, pk):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import get_object_or_404, redirect, render

    from .services.cv_duplicates import delete_stored_file

    if (
        not request.user.is_superuser
        and not request.user.has_perm(
            "rrhh.delete_candidatura"
        )
    ):
        raise PermissionDenied

    candidatura = get_object_or_404(
        Candidatura.objects.select_related(
            "proceso",
            "proceso__team",
            "candidato",
        ),
        pk=pk,
        proceso__team__in=_recruitment_teams(request.user),
    )

    candidate_application_count = (
        candidatura.candidato.candidaturas.count()
    )

    if request.method != "POST":
        return render(
            request,
            "rrhh/candidatura_confirm_action.html",
            {
                "candidatura": candidatura,
                "action_mode": "delete_application",
                "candidate_application_count": (
                    candidate_application_count
                ),
            },
        )

    proceso = candidatura.proceso
    candidato = candidatura.candidato
    candidatura_id = candidatura.pk
    candidato_id = candidato.pk

    storage = (
        candidatura.cv_fichero.storage
        if candidatura.cv_fichero
        else None
    )
    stored_name = (
        candidatura.cv_fichero.name
        if candidatura.cv_fichero
        else ""
    )

    with transaction.atomic():
        registrar_actividad(
            modulo="RRHH",
            accion="ELIMINAR_CANDIDATURA",
            actor=request.user,
            objeto=proceso,
            descripcion=(
                f"Eliminó la candidatura de "
                f"{candidato.nombre_completo} "
                f"del proceso {proceso.titulo}."
            ),
            url=reverse(
                "rrhh:proceso_seleccion_detail",
                kwargs={"pk": proceso.pk},
            ),
            visibilidad=(
                ActividadPlataforma.Visibilidad.EQUIPO
            ),
            metadata={
                "candidatura_id": candidatura_id,
                "candidato_id": candidato_id,
                "cv_eliminado": bool(stored_name),
            },
        )

        candidatura.delete()

        candidate_deleted = False
        if not Candidatura.objects.filter(
            candidato=candidato
        ).exists():
            candidato.delete()
            candidate_deleted = True

        if storage and stored_name:
            transaction.on_commit(
                lambda s=storage, n=stored_name: (
                    delete_stored_file(s, n)
                )
            )

    messages.success(
        request,
        (
            "Candidatura eliminada."
            + (
                " El candidato huérfano también fue eliminado."
                if candidate_deleted
                else ""
            )
        ),
    )
    return redirect(
        "rrhh:proceso_seleccion_detail",
        pk=proceso.pk,
    )
