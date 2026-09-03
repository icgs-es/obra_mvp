from .activity import registrar_operacion_documental
from django.views.decorators.clickjacking import xframe_options_sameorigin
import mimetypes
import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden, FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from urllib.parse import urlencode
from pathlib import PurePosixPath

from django import forms
from .forms import CarpetaForm # 👈 importar el form
from .models import Carpeta, Archivo, ArchivoLog
from .activity import (
    registrar_subida_documental,
    ruta_carpeta_local,
)
from .team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)
from .storage_providers import (
    StorageProviderError,
    get_storage_provider,
)

class SubirArchivoForm(forms.ModelForm):
    class Meta:
        model = Archivo
        fields = ["fichero", "descripcion"]

def with_next(url: str, request):
    nxt = request.GET.get("next")
    return f"{url}?{urlencode({'next': nxt})}" if nxt else url

@login_required
def explorador_raiz(request):
    """
    Lista las carpetas raíz visibles para el usuario actual.
    """
    user = request.user

    carpetas = [
        carpeta
        for carpeta in Carpeta.objects.filter(parent__isnull=True).order_by("nombre")
        if carpeta.puede_ver(user)
    ]

    return render(request, "archivos/explorador_raiz.html", {"carpetas": carpetas})

@login_required
def explorador_carpeta(request, pk):
    carpeta = get_object_or_404(Carpeta, pk=pk)

    # --- Breadcrumbs (ruta desde raíz hasta la carpeta actual) ---
    breadcrumbs = []
    node = carpeta

    # Intentamos detectar el campo "padre" sin asumir el nombre
    parent_attr = None
    for candidate in ("padre", "parent", "carpeta_padre"):
        if hasattr(node, candidate):
            parent_attr = candidate
            break

    # Construimos la cadena de padres
    while node:
        breadcrumbs.append(node)
        node = getattr(node, parent_attr) if parent_attr else None

    breadcrumbs.reverse()

    if not carpeta.puede_ver(request.user):
        return HttpResponseForbidden("No tienes permisos para ver esta carpeta.")

    subcarpetas = [
        c for c in carpeta.hijas.all().order_by("nombre")
        if c.puede_ver(request.user)
    ]
    archivos = carpeta.archivos.all().order_by("-created_at")

    form = SubirArchivoForm()

    context = {
        "carpeta": carpeta,
        "subcarpetas": subcarpetas,
        "archivos": archivos,
        "form": form,
        "breadcrumbs": breadcrumbs,
    }
    # return render(request, "archivos/explorador_carpeta.html", context)
    return render(request, "archivos/archivos_list.html", context)




@login_required
def subir_archivo(request, pk):
    carpeta = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    fallback_url = reverse(
        "archivos:explorador_carpeta",
        kwargs={"pk": carpeta.pk},
    )

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden(
            "No tienes permisos para subir archivos aquí."
        )

    if request.method != "POST":
        return redirect_next(
            request,
            fallback_url,
        )

    form = SubirArchivoForm(
        request.POST,
        request.FILES,
    )

    if not form.is_valid():
        messages.error(
            request,
            "Revisa el formulario de subida.",
        )

        return redirect_next(
            request,
            fallback_url,
        )

    descripcion = form.cleaned_data.get(
        "descripcion",
        "",
    )

    ficheros = request.FILES.getlist(
        "fichero"
    )

    if not ficheros:
        messages.error(
            request,
            "Selecciona al menos un archivo.",
        )

        return redirect_next(
            request,
            fallback_url,
        )

    try:
        team = resolve_document_team(
            request,
            folder=carpeta,
        )
    except DocumentTeamResolutionError as exc:
        messages.error(request, str(exc))

        return redirect_next(
            request,
            fallback_url,
        )

    created_archivos = []

    with transaction.atomic():
        for fichero in ficheros:
            nombre_base, _extension = (
                os.path.splitext(
                    os.path.basename(
                        fichero.name
                    )
                )
            )

            ultima = (
                Archivo.objects
                .filter(
                    carpeta=carpeta,
                    nombre_logico=nombre_base,
                )
                .order_by("-version")
                .first()
            )

            nueva_version = (
                ultima.version + 1
                if ultima
                else 1
            )

            archivo = Archivo.objects.create(
                carpeta=carpeta,
                team=team,
                fichero=fichero,
                nombre_original=fichero.name,
                nombre_logico=nombre_base,
                version=nueva_version,
                descripcion=descripcion,
                subido_por=request.user,
            )

            ArchivoLog.objects.create(
                archivo=archivo,
                usuario=request.user,
                accion="SUBIR",
                detalle=(
                    "Subida de archivo "
                    f"(v{nueva_version})"
                ),
            )

            created_archivos.append(archivo)

        registrar_subida_documental(
            actor=request.user,
            team=team,
            archivos=created_archivos,
            destino=ruta_carpeta_local(
                carpeta
            ),
            url=fallback_url,
            storage_provider="local",
        )

    messages.success(
        request,
        f"Subidos {len(created_archivos)} archivo(s).",
    )

    return redirect_next(
        request,
        fallback_url,
    )




@login_required
def carpeta_raiz_create(request):
    """
    Crear una carpeta raíz con permiso documental explícito.
    """
    if not (
        request.user.is_superuser
        or request.user.has_perm("archivos.add_carpeta")
    ):
        return HttpResponseForbidden(
            "No tienes permisos para crear carpetas raíz."
        )

    if request.method == "POST":
        form = CarpetaForm(request.POST)

        if form.is_valid():
            try:
                team = resolve_document_team(
                    request
                )
            except DocumentTeamResolutionError as exc:
                form.add_error(
                    None,
                    str(exc),
                )
                messages.error(
                    request,
                    str(exc),
                )
            else:
                with transaction.atomic():
                    carpeta = form.save(
                        commit=False
                    )
                    carpeta.owner = (
                        request.user
                    )
                    carpeta.parent = None
                    carpeta.team = team
                    carpeta.save()

                    registrar_operacion_documental(
                        actor=request.user,
                        team=team,
                        accion="crear_carpeta",
                        tipo_elemento="carpeta",
                        nombre=carpeta.nombre,
                        ruta_destino="Archivos",
                        url=reverse(
                            "archivos:explorador_carpeta",
                            kwargs={
                                "pk": carpeta.pk,
                            },
                        ),
                        storage_provider="local",
                        objeto=carpeta,
                    )

                messages.success(
                    request,
                    "Carpeta principal creada correctamente.",
                )

                return redirect(
                    "archivos:explorador_raiz"
                )
    else:
        form = CarpetaForm()

    cancel_url = reverse(
        "archivos:explorador_raiz"
    )

    return render(
        request,
        "archivos/carpeta_form.html",
        {
            "form": form,
            "carpeta_padre": None,
            "titulo": "Nueva carpeta principal",
            "cancel_url": cancel_url,
        },
    )



@login_required
def subcarpeta_create(
    request,
    carpeta_id,
):
    """
    Crear una subcarpeta dentro de
    una carpeta existente.
    """
    carpeta_padre = get_object_or_404(
        Carpeta,
        pk=carpeta_id,
    )

    if not (
        carpeta_padre.puede_escribir(request.user)
        and (
            request.user.is_superuser
            or carpeta_padre.owner == request.user
            or request.user.has_perm("archivos.add_carpeta")
        )
    ):
        return HttpResponseForbidden(
            "No tienes permiso para crear subcarpetas aquí."
        )

    if request.method == "POST":
        form = CarpetaForm(request.POST)

        if form.is_valid():
            try:
                team = resolve_document_team(
                    request,
                    folder=carpeta_padre,
                )
            except DocumentTeamResolutionError as exc:
                form.add_error(
                    None,
                    str(exc),
                )
                messages.error(
                    request,
                    str(exc),
                )
            else:
                with transaction.atomic():
                    sub = form.save(
                        commit=False
                    )
                    sub.parent = (
                        carpeta_padre
                    )
                    sub.owner = request.user
                    sub.team = team
                    sub.save()

                    registrar_operacion_documental(
                        actor=request.user,
                        team=team,
                        accion="crear_carpeta",
                        tipo_elemento="carpeta",
                        nombre=sub.nombre,
                        ruta_destino=(
                            ruta_carpeta_local(
                                carpeta_padre
                            )
                        ),
                        url=reverse(
                            "archivos:explorador_carpeta",
                            kwargs={
                                "pk": sub.pk,
                            },
                        ),
                        storage_provider="local",
                        objeto=sub,
                    )

                messages.success(
                    request,
                    "Subcarpeta creada correctamente.",
                )

                fallback_url = reverse(
                    "archivos:explorador_carpeta",
                    kwargs={
                        "pk": carpeta_padre.pk
                    },
                )

                return redirect_next(
                    request,
                    fallback_url,
                )
    else:
        form = CarpetaForm()

    cancel_url_base = reverse(
        "archivos:explorador_carpeta",
        kwargs={
            "pk": carpeta_padre.pk
        },
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/carpeta_form.html",
        {
            "form": form,
            "carpeta_padre": (
                carpeta_padre
            ),
            "titulo": (
                "Nueva subcarpeta en "
                f"«{carpeta_padre.nombre}»"
            ),
            "cancel_url": cancel_url,
        },
    )


# ... resto de imports y vistas que ya tienes ...

@login_required
def carpeta_renombrar(request, pk):
    carpeta = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    if not carpeta.puede_escribir(
        request.user
    ):
        return HttpResponseForbidden(
            "No tienes permisos para renombrar esta carpeta."
        )

    if request.method == "POST":
        form = CarpetaForm(
            request.POST,
            instance=carpeta,
        )

        if form.is_valid():
            nombre_anterior = (
                carpeta.nombre
            )

            ruta_anterior = (
                ruta_carpeta_local(
                    carpeta.parent
                )
                if carpeta.parent
                else "Archivos"
            )

            with transaction.atomic():
                carpeta = form.save()

                if (
                    nombre_anterior
                    != carpeta.nombre
                ):
                    registrar_operacion_documental(
                        actor=request.user,
                        team=carpeta.team,
                        accion="renombrar",
                        tipo_elemento="carpeta",
                        nombre_anterior=(
                            nombre_anterior
                        ),
                        nombre_nuevo=(
                            carpeta.nombre
                        ),
                        ruta_origen=(
                            ruta_anterior
                        ),
                        ruta_destino=(
                            ruta_anterior
                        ),
                        url=reverse(
                            "archivos:explorador_carpeta",
                            kwargs={
                                "pk": carpeta.pk,
                            },
                        ),
                        storage_provider="local",
                        objeto=carpeta,
                    )

            messages.success(
                request,
                "Carpeta renombrada correctamente.",
            )

            if carpeta.parent:
                fallback_url = reverse(
                    "archivos:explorador_carpeta",
                    kwargs={
                        "pk": carpeta.parent.pk
                    },
                )
            else:
                fallback_url = reverse(
                    "archivos:explorador_raiz"
                )

            return redirect_next(
                request,
                fallback_url,
            )
    else:
        form = CarpetaForm(
            instance=carpeta
        )

    cancel_url_base = (
        reverse(
            "archivos:explorador_carpeta",
            kwargs={
                "pk": carpeta.parent.pk
            },
        )
        if carpeta.parent
        else reverse(
            "archivos:explorador_raiz"
        )
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/carpeta_renombrar.html",
        {
            "form": form,
            "carpeta": carpeta,
            "cancel_url": cancel_url,
        },
    )

@login_required
def carpeta_eliminar(request, pk):
    carpeta = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    if not carpeta.puede_escribir(
        request.user
    ):
        return HttpResponseForbidden(
            "No tienes permisos para eliminar esta carpeta."
        )

    tiene_subcarpetas = (
        carpeta.hijas.exists()
    )

    tiene_archivos = (
        carpeta.archivos.exists()
    )

    if request.method == "POST":
        parent = carpeta.parent
        nombre = carpeta.nombre
        folder_id = carpeta.pk
        team = carpeta.team

        ruta_parent = (
            ruta_carpeta_local(parent)
            if parent
            else "Archivos"
        )

        def tree_stats(node):
            folder_count = 1
            file_count = (
                node.archivos.count()
            )

            for child in (
                node.hijas.all()
            ):
                (
                    child_folders,
                    child_files,
                ) = tree_stats(child)

                folder_count += (
                    child_folders
                )
                file_count += child_files

            return (
                folder_count,
                file_count,
            )

        (
            carpetas_totales,
            archivos_totales,
        ) = tree_stats(carpeta)

        with transaction.atomic():
            carpeta.delete()

            registrar_operacion_documental(
                actor=request.user,
                team=team,
                accion="eliminar",
                tipo_elemento="carpeta",
                nombre=nombre,
                ruta_origen=ruta_parent,
                url=(
                    reverse(
                        "archivos:explorador_carpeta",
                        kwargs={
                            "pk": parent.pk,
                        },
                    )
                    if parent
                    else reverse(
                        "archivos:explorador_raiz"
                    )
                ),
                storage_provider="local",
                objeto=None,
                tipo_objeto=(
                    "archivos.carpeta"
                ),
                objeto_id=folder_id,
                metadata_extra={
                    "subcarpetas_eliminadas": (
                        max(
                            carpetas_totales - 1,
                            0,
                        )
                    ),
                    "archivos_eliminados": (
                        archivos_totales
                    ),
                },
            )

        messages.success(
            request,
            (
                f"Carpeta «{nombre}» y todo "
                "su contenido se han eliminado "
                "correctamente."
            ),
        )

        if parent:
            fallback_url = reverse(
                "archivos:explorador_carpeta",
                kwargs={
                    "pk": parent.pk
                },
            )
        else:
            fallback_url = reverse(
                "archivos:explorador_raiz"
            )

        return redirect_next(
            request,
            fallback_url,
        )

    cancel_url_base = (
        reverse(
            "archivos:explorador_carpeta",
            kwargs={
                "pk": carpeta.parent.pk
            },
        )
        if carpeta.parent
        else reverse(
            "archivos:explorador_raiz"
        )
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/carpeta_eliminar_confirm.html",
        {
            "carpeta": carpeta,
            "tiene_subcarpetas": (
                tiene_subcarpetas
            ),
            "tiene_archivos": (
                tiene_archivos
            ),
            "cancel_url": cancel_url,
        },
    )

@login_required
def archivo_eliminar(request, pk):
    archivo = get_object_or_404(
        Archivo,
        pk=pk,
    )

    carpeta = archivo.carpeta

    if not carpeta.puede_escribir(
        request.user
    ):
        return HttpResponseForbidden(
            "No tienes permisos para eliminar archivos aquí."
        )

    fallback_url = reverse(
        "archivos:explorador_carpeta",
        kwargs={"pk": carpeta.pk},
    )

    if request.method == "POST":
        nombre = (
            archivo.nombre_original
            or archivo.nombre_logico
            or str(archivo)
        )

        archivo_id = archivo.pk
        team = (
            archivo.team
            or carpeta.team
        )

        ruta = ruta_carpeta_local(
            carpeta
        )

        with transaction.atomic():
            ArchivoLog.objects.create(
                archivo=archivo,
                usuario=request.user,
                accion="ELIMINAR",
                detalle=(
                    f"Eliminado archivo "
                    f"«{nombre}»"
                ),
            )

            archivo.delete()

            registrar_operacion_documental(
                actor=request.user,
                team=team,
                accion="eliminar",
                tipo_elemento="archivo",
                nombre=nombre,
                ruta_origen=ruta,
                url=fallback_url,
                storage_provider="local",
                objeto=None,
                tipo_objeto=(
                    "archivos.archivo"
                ),
                objeto_id=archivo_id,
            )

        messages.success(
            request,
            (
                f"Archivo «{nombre}» "
                "eliminado correctamente."
            ),
        )

        return redirect_next(
            request,
            fallback_url,
        )

    cancel_url = with_next(
        fallback_url,
        request,
    )

    return render(
        request,
        "archivos/archivo_eliminar_confirm.html",
        {
            "archivo": archivo,
            "carpeta": carpeta,
            "cancel_url": cancel_url,
        },
    )

@require_POST
@csrf_protect
@login_required
def eliminar_archivos_masivo(
    request,
    pk,
):
    carpeta = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    if not carpeta.puede_escribir(
        request.user
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Sin permisos",
            },
            status=403,
        )

    ids = request.POST.getlist("ids")

    if not ids:
        return JsonResponse(
            {
                "ok": False,
                "error": "Sin ids",
            },
            status=400,
        )

    try:
        archivos = list(
            Archivo.objects
            .filter(
                carpeta=carpeta,
                id__in=ids,
            )
            .select_related(
                "team",
                "carpeta",
            )
            .order_by("id")
        )

        if not archivos:
            return JsonResponse({
                "ok": True,
                "deleted": 0,
            })

        nombres = [
            (
                item.nombre_original
                or item.nombre_logico
                or str(item)
            )
            for item in archivos
        ]

        archivo_ids = [
            item.pk
            for item in archivos
        ]

        team_ids = {
            item.team_id
            for item in archivos
            if item.team_id
        }

        if len(team_ids) == 1:
            team = next(
                item.team
                for item in archivos
                if item.team_id
            )

        elif (
            not team_ids
            and carpeta.team_id
        ):
            team = carpeta.team

        else:
            team = None

        ruta = ruta_carpeta_local(
            carpeta
        )

        with transaction.atomic():
            for item in archivos:
                ArchivoLog.objects.create(
                    archivo=item,
                    usuario=request.user,
                    accion="ELIMINAR",
                    detalle=(
                        "Eliminación masiva"
                    ),
                )

            (
                Archivo.objects
                .filter(
                    pk__in=archivo_ids
                )
                .delete()
            )

            registrar_operacion_documental(
                actor=request.user,
                team=team,
                accion="eliminar",
                tipo_elemento="archivos",
                ruta_origen=ruta,
                url=reverse(
                    "archivos:explorador_carpeta",
                    kwargs={
                        "pk": carpeta.pk
                    },
                ),
                storage_provider="local",
                objeto=None,
                tipo_objeto=(
                    "archivos.eliminacion_documental"
                ),
                objeto_id=archivo_ids[0],
                cantidad=len(
                    archivo_ids
                ),
                nombres=nombres,
                metadata_extra={
                    "archivo_ids": (
                        archivo_ids[:100]
                    ),
                    "archivo_ids_truncados": (
                        len(archivo_ids) > 100
                    ),
                },
            )

        return JsonResponse({
            "ok": True,
            "deleted": len(
                archivo_ids
            ),
        })

    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status=500,
        )

@login_required
def archivo_detalle(request, pk):
    archivo = get_object_or_404(Archivo, pk=pk)
    carpeta = archivo.carpeta

    # Permiso de lectura básico
    if not carpeta.puede_ver(request.user):
        return HttpResponseForbidden("No tienes permisos para ver este archivo.")

    next_url = request.GET.get("next")
    if not next_url:
        next_url = reverse("archivos:explorador_carpeta", args=[archivo.carpeta_id])

    return render(
        request,
        "archivos/archivo_detalle.html",
        {
            "archivo": archivo,
            "carpeta": carpeta,
            "next_url": next_url,
        },
    )

@login_required
def archivo_renombrar(request, pk):
    archivo = get_object_or_404(
        Archivo,
        pk=pk,
    )

    carpeta = archivo.carpeta

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden(
            "No tienes permisos para renombrar este archivo."
        )

    form_url = reverse(
        "archivos:archivo_renombrar",
        kwargs={"pk": archivo.pk},
    )

    if request.method == "POST":
        nuevo_nombre = (
            request.POST.get(
                "nombre_original",
                "",
            )
            .strip()
        )

        if not nuevo_nombre:
            messages.error(
                request,
                "El nombre no puede estar vacío.",
            )

            return redirect_next(
                request,
                form_url,
            )

        viejo = (
            archivo.nombre_original
        )

        if viejo == nuevo_nombre:
            messages.info(
                request,
                "El archivo ya tiene ese nombre.",
            )

            fallback_url = reverse(
                "archivos:explorador_carpeta",
                kwargs={
                    "pk": carpeta.pk
                },
            )

            return redirect_next(
                request,
                fallback_url,
            )

        with transaction.atomic():
            archivo.nombre_original = (
                nuevo_nombre
            )
            archivo.save(
                update_fields=[
                    "nombre_original",
                ]
            )

            ArchivoLog.objects.create(
                archivo=archivo,
                usuario=request.user,
                accion="RENOMBRAR",
                detalle=(
                    f"De '{viejo}' a "
                    f"'{nuevo_nombre}'"
                ),
            )

            registrar_operacion_documental(
                actor=request.user,
                team=(
                    archivo.team
                    or carpeta.team
                ),
                accion="renombrar",
                tipo_elemento="archivo",
                nombre_anterior=viejo,
                nombre_nuevo=(
                    nuevo_nombre
                ),
                ruta_origen=(
                    ruta_carpeta_local(
                        carpeta
                    )
                ),
                ruta_destino=(
                    ruta_carpeta_local(
                        carpeta
                    )
                ),
                url=reverse(
                    "archivos:archivo_detalle",
                    kwargs={
                        "pk": archivo.pk
                    },
                ),
                storage_provider="local",
                objeto=archivo,
            )

        messages.success(
            request,
            "Archivo renombrado correctamente.",
        )

        fallback_url = reverse(
            "archivos:explorador_carpeta",
            kwargs={"pk": carpeta.pk},
        )

        return redirect_next(
            request,
            fallback_url,
        )

    cancel_url_base = reverse(
        "archivos:explorador_carpeta",
        kwargs={"pk": carpeta.pk},
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/archivo_renombrar.html",
        {
            "archivo": archivo,
            "carpeta": carpeta,
            "cancel_url": cancel_url,
        },
    )
    
@login_required
def archivo_mover(request, pk):
    archivo = get_object_or_404(
        Archivo,
        pk=pk,
    )

    carpeta_origen = archivo.carpeta

    if not carpeta_origen.puede_escribir(request.user):
        return HttpResponseForbidden(
            "No tienes permisos para mover este archivo."
        )

    if request.user.is_superuser or request.user.has_perm("archivos.change_archivo"):
        candidates = (
            Carpeta.objects
            .exclude(pk=carpeta_origen.pk)
            .select_related("team")
            .order_by("nombre")
        )
    else:
        candidates = (
            Carpeta.objects
            .filter(owner=request.user)
            .exclude(pk=carpeta_origen.pk)
            .select_related("team")
            .order_by("nombre")
        )

    effective_team_id = (
        archivo.team_id
        or carpeta_origen.team_id
    )

    if effective_team_id:
        carpetas_destino = [
            item
            for item in candidates
            if item.team_id in (
                None,
                effective_team_id,
            )
        ]
    else:
        carpetas_destino = list(
            candidates
        )

    form_url = reverse(
        "archivos:archivo_mover",
        kwargs={"pk": archivo.pk},
    )

    if request.method == "POST":
        destino_id = str(
            request.POST.get(
                "carpeta_destino",
            )
            or ""
        ).strip()

        if not destino_id.isdigit():
            messages.error(
                request,
                "Selecciona una carpeta destino válida.",
            )

            return redirect_next(
                request,
                form_url,
            )

        carpeta_destino = (
            get_object_or_404(
                Carpeta,
                pk=int(destino_id),
            )
        )

        if not carpeta_destino.puede_escribir(request.user):
            return HttpResponseForbidden(
                "No tienes permisos para mover a esa carpeta."
            )

        if (
            carpeta_destino.pk
            == carpeta_origen.pk
        ):
            messages.warning(
                request,
                "El archivo ya está en esa carpeta.",
            )

            fallback_url = reverse(
                "archivos:explorador_carpeta",
                kwargs={
                    "pk": carpeta_origen.pk
                },
            )

            return redirect_next(
                request,
                fallback_url,
            )

        source_team_id = (
            archivo.team_id
            or carpeta_origen.team_id
        )

        destination_team_id = (
            carpeta_destino.team_id
        )

        if (
            source_team_id
            and destination_team_id
            and source_team_id
            != destination_team_id
        ):
            return HttpResponseForbidden(
                "No se puede mover un archivo "
                "entre empresas diferentes."
            )

        ruta_origen = (
            ruta_carpeta_local(
                carpeta_origen
            )
        )

        ruta_destino = (
            ruta_carpeta_local(
                carpeta_destino
            )
        )

        nombre = (
            archivo.nombre_original
            or archivo.nombre_logico
            or str(archivo)
        )

        with transaction.atomic():
            archivo.carpeta = (
                carpeta_destino
            )

            update_fields = [
                "carpeta",
            ]

            if (
                archivo.team_id is None
                and carpeta_destino.team_id
            ):
                archivo.team = (
                    carpeta_destino.team
                )
                update_fields.append(
                    "team"
                )

            archivo.save(
                update_fields=update_fields
            )

            ArchivoLog.objects.create(
                archivo=archivo,
                usuario=request.user,
                accion="MOVER",
                detalle=(
                    f"De '{ruta_origen}' "
                    f"a '{ruta_destino}'"
                ),
            )

            registrar_operacion_documental(
                actor=request.user,
                team=(
                    archivo.team
                    or carpeta_destino.team
                    or carpeta_origen.team
                ),
                accion="mover",
                tipo_elemento="archivo",
                nombre=nombre,
                ruta_origen=(
                    ruta_origen
                ),
                ruta_destino=(
                    ruta_destino
                ),
                url=reverse(
                    "archivos:archivo_detalle",
                    kwargs={
                        "pk": archivo.pk
                    },
                ),
                storage_provider="local",
                objeto=archivo,
            )

        messages.success(
            request,
            (
                "Archivo movido a "
                f"«{carpeta_destino.nombre}»."
            ),
        )

        fallback_url = reverse(
            "archivos:explorador_carpeta",
            kwargs={
                "pk": carpeta_destino.pk
            },
        )

        return redirect_next(
            request,
            fallback_url,
        )

    cancel_url_base = reverse(
        "archivos:explorador_carpeta",
        kwargs={
            "pk": carpeta_origen.pk
        },
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/archivo_mover.html",
        {
            "archivo": archivo,
            "carpeta_origen": (
                carpeta_origen
            ),
            "carpetas_destino": (
                carpetas_destino
            ),
            "cancel_url": cancel_url,
        },
    )

@login_required
def carpeta_mover(request, pk):
    carpeta = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden(
            "No tienes permisos para mover esta carpeta."
        )

    if request.user.is_superuser or request.user.has_perm("archivos.change_carpeta"):
        candidates = (
            Carpeta.objects
            .exclude(pk=carpeta.pk)
            .select_related("team")
        )
    else:
        candidates = (
            Carpeta.objects
            .filter(owner=request.user)
            .exclude(pk=carpeta.pk)
            .select_related("team")
        )

    carpetas_destino = [
        candidate
        for candidate in candidates
        if (
            not carpeta.es_ancestro_de(
                candidate
            )
            and candidate.team_id
            == carpeta.team_id
        )
    ]

    if request.method == "POST":
        destino_id = str(
            request.POST.get(
                "carpeta_destino",
            )
            or ""
        ).strip()

        if destino_id == "":
            messages.error(
                request,
                "Selecciona una carpeta destino.",
            )

            fallback_url = reverse(
                "archivos:carpeta_mover",
                kwargs={
                    "pk": carpeta.pk
                },
            )

            return redirect_next(
                request,
                fallback_url,
            )

        ruta_anterior = (
            ruta_carpeta_local(
                carpeta
            )
        )

        old_parent = carpeta.parent

        if destino_id == "ROOT":
            if carpeta.parent_id is None:
                messages.info(
                    request,
                    (
                        "La carpeta ya está "
                        "en el nivel raíz."
                    ),
                )

                return redirect_next(
                    request,
                    reverse(
                        "archivos:explorador_raiz"
                    ),
                )

            with transaction.atomic():
                carpeta.parent = None
                carpeta.save(
                    update_fields=[
                        "parent",
                        "updated_at",
                    ]
                )

                registrar_operacion_documental(
                    actor=request.user,
                    team=carpeta.team,
                    accion="mover",
                    tipo_elemento="carpeta",
                    nombre=carpeta.nombre,
                    ruta_origen=(
                        ruta_anterior
                    ),
                    ruta_destino=(
                        ruta_carpeta_local(
                            carpeta
                        )
                    ),
                    url=reverse(
                        "archivos:explorador_carpeta",
                        kwargs={
                            "pk": carpeta.pk
                        },
                    ),
                    storage_provider="local",
                    objeto=carpeta,
                    metadata_extra={
                        "parent_anterior_id": (
                            old_parent.pk
                            if old_parent
                            else None
                        ),
                        "parent_nuevo_id": None,
                    },
                )

            messages.success(
                request,
                "Carpeta movida a nivel raíz.",
            )

            return redirect_next(
                request,
                reverse(
                    "archivos:explorador_raiz"
                ),
            )

        if not destino_id.isdigit():
            messages.error(
                request,
                "Destino no válido.",
            )

            fallback_url = reverse(
                "archivos:carpeta_mover",
                kwargs={
                    "pk": carpeta.pk
                },
            )

            return redirect_next(
                request,
                fallback_url,
            )

        carpeta_destino = (
            get_object_or_404(
                Carpeta,
                pk=int(destino_id),
            )
        )

        if (
            carpeta_destino.pk
            == carpeta.pk
            or carpeta.es_ancestro_de(
                carpeta_destino
            )
        ):
            messages.error(
                request,
                (
                    "No se puede mover una carpeta "
                    "dentro de sí misma."
                ),
            )

            fallback_url = reverse(
                "archivos:carpeta_mover",
                kwargs={
                    "pk": carpeta.pk
                },
            )

            return redirect_next(
                request,
                fallback_url,
            )

        if (
            carpeta_destino.team_id
            != carpeta.team_id
        ):
            return HttpResponseForbidden(
                "No se puede mover una carpeta "
                "entre ámbitos empresariales diferentes."
            )

        ruta_destino_parent = (
            ruta_carpeta_local(
                carpeta_destino
            )
        )

        with transaction.atomic():
            carpeta.parent = (
                carpeta_destino
            )
            carpeta.save(
                update_fields=[
                    "parent",
                    "updated_at",
                ]
            )

            registrar_operacion_documental(
                actor=request.user,
                team=carpeta.team,
                accion="mover",
                tipo_elemento="carpeta",
                nombre=carpeta.nombre,
                ruta_origen=(
                    ruta_anterior
                ),
                ruta_destino=(
                    ruta_carpeta_local(
                        carpeta
                    )
                ),
                url=reverse(
                    "archivos:explorador_carpeta",
                    kwargs={
                        "pk": carpeta.pk
                    },
                ),
                storage_provider="local",
                objeto=carpeta,
                metadata_extra={
                    "parent_anterior_id": (
                        old_parent.pk
                        if old_parent
                        else None
                    ),
                    "parent_nuevo_id": (
                        carpeta_destino.pk
                    ),
                    "ruta_destino_parent": (
                        ruta_destino_parent
                    ),
                },
            )

        messages.success(
            request,
            (
                "Carpeta movida a "
                f"«{ruta_destino_parent}»."
            ),
        )

        fallback_url = reverse(
            "archivos:explorador_carpeta",
            kwargs={
                "pk": carpeta_destino.pk
            },
        )

        return redirect_next(
            request,
            fallback_url,
        )

    cancel_url_base = (
        reverse(
            "archivos:explorador_carpeta",
            kwargs={
                "pk": carpeta.parent.pk
            },
        )
        if carpeta.parent
        else reverse(
            "archivos:explorador_raiz"
        )
    )

    cancel_url = with_next(
        cancel_url_base,
        request,
    )

    return render(
        request,
        "archivos/carpeta_mover.html",
        {
            "carpeta": carpeta,
            "carpetas_destino": (
                carpetas_destino
            ),
            "cancel_url": cancel_url,
        },
    )




@require_POST
@login_required
def subir_carpeta(request, pk):
    carpeta_base = get_object_or_404(
        Carpeta,
        pk=pk,
    )

    if not carpeta_base.puede_escribir(
        request.user
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Sin permisos",
            },
            status=403,
        )

    files = request.FILES.getlist("files")
    relpaths = request.POST.getlist("relpath")

    keep_root = request.POST.get(
        "keep_root"
    ) in (
        "1",
        "true",
        "True",
        "yes",
        "on",
    )

    if not files:
        return JsonResponse(
            {
                "ok": False,
                "error": "No hay archivos",
            },
            status=400,
        )

    if len(relpaths) != len(files):
        return JsonResponse(
            {
                "ok": False,
                "error": "Datos incompletos",
            },
            status=400,
        )

    try:
        team = resolve_document_team(
            request,
            folder=carpeta_base,
        )
    except DocumentTeamResolutionError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status=409,
        )

    created = 0
    created_folders = 0
    created_archivos = []
    cache = {}

    def get_or_create_child(
        parent: Carpeta,
        name: str,
    ) -> Carpeta:
        nonlocal created_folders

        key = (
            parent.pk,
            name,
        )

        if key in cache:
            return cache[key]

        obj, was_created = (
            Carpeta.objects.get_or_create(
                parent=parent,
                nombre=name,
                defaults={
                    "owner": request.user,
                    "team": parent.team or team,
                    "visibilidad": parent.visibilidad,
                    "departamento": (
                        getattr(
                            parent,
                            "departamento",
                            None,
                        )
                    ),
                },
            )
        )

        if (
            obj.team_id
            and obj.team_id != team.id
        ):
            raise DocumentTeamResolutionError(
                "La carpeta importada coincide "
                "con otra empresa."
            )

        if was_created:
            created_folders += 1

        cache[key] = obj
        return obj

    try:
        with transaction.atomic():
            for fichero, relpath in zip(
                files,
                relpaths,
            ):
                path = PurePosixPath(relpath)

                parts = [
                    value
                    for value in path.parts
                    if value not in (
                        "",
                        ".",
                        "..",
                    )
                ]

                if (
                    not keep_root
                    and len(parts) > 1
                ):
                    parts = parts[1:]

                if len(parts) == 1:
                    current = carpeta_base
                else:
                    current = carpeta_base

                    for folder_name in parts[:-1]:
                        current = (
                            get_or_create_child(
                                current,
                                folder_name,
                            )
                        )

                current_team = (
                    current.team
                    or team
                )

                if current_team.id != team.id:
                    raise DocumentTeamResolutionError(
                        "La carpeta de destino pertenece "
                        "a otra empresa."
                    )

                archivo = Archivo.objects.create(
                    carpeta=current,
                    team=current_team,
                    fichero=fichero,
                    nombre_original=fichero.name,
                    descripcion="",
                    subido_por=request.user,
                )

                ArchivoLog.objects.create(
                    archivo=archivo,
                    usuario=request.user,
                    accion="SUBIR",
                    detalle=(
                        "Subida dentro de carpeta "
                        f"importada ({relpath})"
                    ),
                )

                created_archivos.append(archivo)
                created += 1

            registrar_subida_documental(
                actor=request.user,
                team=team,
                archivos=created_archivos,
                destino=ruta_carpeta_local(
                    carpeta_base
                ),
                url=reverse(
                    "archivos:explorador_carpeta",
                    kwargs={
                        "pk": carpeta_base.pk
                    },
                ),
                storage_provider="local",
                carpetas_creadas=(
                    created_folders
                ),
            )

    except DocumentTeamResolutionError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "files": created,
            "folders": created_folders,
        }
    )


    
def redirect_next(request, fallback_url):
    """
    Redirige a ?next=... si es seguro.
    Si no existe o no es seguro, redirige a fallback_url.
    """
    next_url = request.GET.get("next") or request.POST.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect(fallback_url)

def _check_perm(user, archivo):
    carpeta = archivo.carpeta

    if carpeta.visibilidad == "GLOBAL":
        return True

    if carpeta.visibilidad == "PRIVADA":
        return (carpeta.owner_id == user.id) or user.is_superuser

    if carpeta.visibilidad == "DEPTO":
        return user.groups.filter(id=carpeta.departamento_id).exists() or user.is_superuser

    return False

def _can_access_file(user, archivo: Archivo) -> bool:
    # Regla simple y segura: se hereda de la carpeta
    # (tú ya tienes carpeta.puede_ver)
    try:
        return archivo.carpeta.puede_ver(user)
    except Exception:
        return False

def _guess_content_type(archivo: Archivo) -> str:
    # Intenta por nombre original, si no por path real
    name = getattr(archivo, "nombre_original", "") or ""
    path = getattr(getattr(archivo, "fichero", None), "name", "") or ""
    ctype, _ = mimetypes.guess_type(name or path)
    return ctype or "application/octet-stream"

@login_required
@xframe_options_sameorigin
def file_preview(request, file_id: int):
    a = get_object_or_404(Archivo, pk=file_id)

    if not _can_access_file(request.user, a):
        raise Http404()

    try:
        provider = get_storage_provider(
            a.storage_provider
        )

        if not provider.exists(a):
            raise Http404(
                "El objeto documental no existe."
            )

        fh = provider.open(a, "rb")

    except FileNotFoundError:
        raise Http404(
            "El objeto documental no existe."
        )

    except StorageProviderError:
        from django.http import HttpResponse

        return HttpResponse(
            "El proveedor documental no está disponible "
            "temporalmente.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    content_type = (
        a.mimetype
        or _guess_content_type(a)
        or "application/octet-stream"
    )

    resp = FileResponse(
        fh,
        content_type=content_type,
    )

    filename = (
        a.nombre_original
        or a.nombre_logico
        or "archivo"
    ).replace('"', "")

    resp["Content-Disposition"] = (
        f'inline; filename="{filename}"'
    )

    return resp

@login_required
def archivo_descargar(request, file_id: int):
    a = get_object_or_404(Archivo, pk=file_id)

    if not _can_access_file(request.user, a):
        raise Http404()

    try:
        provider = get_storage_provider(
            a.storage_provider
        )

        if not provider.exists(a):
            raise Http404(
                "El objeto documental no existe."
            )

        fh = provider.open(a, "rb")

    except FileNotFoundError:
        raise Http404(
            "El objeto documental no existe."
        )

    except StorageProviderError:
        from django.http import HttpResponse

        return HttpResponse(
            "El proveedor documental no está disponible "
            "temporalmente.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    ArchivoLog.objects.create(
        archivo=a,
        usuario=request.user,
        accion="DESCARGAR",
        detalle=(
            "Descarga desde proveedor "
            f"{a.storage_provider}"
        ),
    )

    content_type = (
        a.mimetype
        or "application/octet-stream"
    )

    resp = FileResponse(
        fh,
        content_type=content_type,
    )

    filename = (
        a.nombre_original
        or a.nombre_logico
        or "archivo"
    ).replace('"', "")

    resp["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    return resp

# Alias para compatibilidad con el nombre antiguo
# (muchos sitios pueden seguir apuntando a archivos:download)
@login_required
def file_download(request, file_id: int):
    return archivo_descargar(request, file_id)

@login_required
def archivo_editar_online(request, file_id: int):
    """
    Abre un documento Office almacenado por un provider externo.

    INTASA valida permisos y solicita al provider una sesión
    efímera. Las credenciales del provider nunca se envían al
    navegador.
    """
    archivo = get_object_or_404(
        Archivo,
        pk=file_id,
    )

    if not _can_access_file(
        request.user,
        archivo,
    ):
        raise Http404()

    try:
        provider = get_storage_provider(
            archivo.storage_provider
        )

        if not provider.supports_online_edit(
            archivo
        ):
            raise Http404(
                "Este documento no admite edición online."
            )

        office_session = (
            provider.create_online_edit_session(
                archivo
            )
        )

        office_error = ""

    except Http404:
        raise

    except StorageProviderError:
        office_session = None
        office_error = (
            "No se pudo iniciar el editor online. "
            "Inténtalo nuevamente."
        )

    next_url = (
        request.GET.get("next")
        or reverse(
            "archivos:archivo_detalle",
            args=[archivo.pk],
        )
    )

    response = render(
        request,
        "archivos/archivo_editor_online.html",
        {
            "archivo": archivo,
            "office": office_session,
            "office_error": office_error,
            "next_url": next_url,
        },
        status=503 if office_error else 200,
    )

    response["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["Referrer-Policy"] = "no-referrer"

    return response
