import mimetypes
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden, FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from urllib.parse import urlencode
from pathlib import PurePosixPath

from django import forms
from .forms import CarpetaForm # 👈 importar el form
from .models import Carpeta, Archivo

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

    if user.is_superuser or user.is_staff:
        carpetas = Carpeta.objects.filter(parent__isnull=True).order_by("nombre")
    else:
        grupos = user.groups.all()
        carpetas = (
            Carpeta.objects
            .filter(parent__isnull=True)
            .filter(
                Q(visibilidad="GLOBAL")
                | Q(visibilidad="PRIVADA", owner=user)
                | Q(visibilidad="DEPTO", departamento__in=grupos)
            )
            .order_by("nombre")
        )

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
    carpeta = get_object_or_404(Carpeta, pk=pk)

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden("No tienes permisos para subir archivos aquí.")

    if request.method != "POST":
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
        return redirect_next(request, fallback_url)

    form = SubirArchivoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Revisa el formulario de subida.")
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
        return redirect_next(request, fallback_url)

    descripcion = form.cleaned_data.get("descripcion", "")

    ficheros = request.FILES.getlist("fichero")
    if not ficheros:
        messages.error(request, "Selecciona al menos un archivo.")
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
        return redirect_next(request, fallback_url)

    for f in ficheros:
        Archivo.objects.create(
            carpeta=carpeta,
            fichero=f,
            nombre_original=f.name,
            descripcion=descripcion,
            subido_por=request.user,
        )

    messages.success(request, f"Subidos {len(ficheros)} archivo(s).")
    fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
    return redirect_next(request, fallback_url)

@login_required
def carpeta_raiz_create(request):
    """
    Crear una carpeta raíz.
    Solo staff / superuser.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden("No tienes permisos para crear carpetas raíz.")

    if request.method == "POST":
        form = CarpetaForm(request.POST)
        if form.is_valid():
            carpeta = form.save(commit=False)
            carpeta.owner = request.user
            carpeta.parent = None
            carpeta.save()
            messages.success(request, "Carpeta principal creada correctamente.")
            return redirect("archivos:explorador_raiz")
    else:
        form = CarpetaForm()

    cancel_url = reverse("archivos:explorador_raiz")

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
def subcarpeta_create(request, carpeta_id):
    """
    Crear una subcarpeta dentro de una carpeta existente.
    """
    carpeta_padre = get_object_or_404(Carpeta, pk=carpeta_id)

    # Permiso básico: superuser, staff o owner de la carpeta padre
    if not (request.user.is_superuser or request.user.is_staff or carpeta_padre.owner == request.user):
        return HttpResponseForbidden("No tienes permiso para crear subcarpetas aquí.")

    if request.method == "POST":
        form = CarpetaForm(request.POST)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.parent = carpeta_padre
            sub.owner = request.user
            sub.save()
            messages.success(request, "Subcarpeta creada correctamente.")
            fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_padre.pk})
            return redirect_next(request, fallback_url)
    else:
        form = CarpetaForm()

    cancel_url_base = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_padre.pk})
    cancel_url = with_next(cancel_url_base, request)

    return render(
        request,
        "archivos/carpeta_form.html",
        {
            "form": form,
            "carpeta_padre": carpeta_padre,
            "titulo": f"Nueva subcarpeta en «{carpeta_padre.nombre}»",
            "cancel_url": cancel_url,
        },
    )

# ... resto de imports y vistas que ya tienes ...

@login_required
def carpeta_renombrar(request, pk):
    """
    Renombrar una carpeta existente.
    Solo si el usuario puede escribir en ella.
    Respeta ?next para volver a la vista exacta (tabla/lista y misma carpeta).
    """
    carpeta = get_object_or_404(Carpeta, pk=pk)

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden("No tienes permisos para renombrar esta carpeta.")

    if request.method == "POST":
        form = CarpetaForm(request.POST, instance=carpeta)
        if form.is_valid():
            form.save()
            messages.success(request, "Carpeta renombrada correctamente.")

            # fallback “natural” si no hay next: volver al padre (o raíz)
            if carpeta.parent:
                fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.parent.pk})
            else:
                fallback_url = reverse("archivos:explorador_raiz")

            return redirect_next(request, fallback_url)

        # Si no es válido, caemos al render mostrando errores (sin redirect)
    else:
        form = CarpetaForm(instance=carpeta)

    cancel_url_base = (
        reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.parent.pk})
        if carpeta.parent
        else reverse("archivos:explorador_raiz")
    )
    cancel_url = with_next(cancel_url_base, request)

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
    """
    Eliminar una carpeta si está vacía (sin subcarpetas ni archivos).
    Respeta el parámetro ?next para volver a vista tabla/lista exacta.
    """
    carpeta = get_object_or_404(Carpeta, pk=pk)

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden("No tienes permisos para eliminar esta carpeta.")

    # OJO: recalcularemos en POST también por seguridad (por si cambió en paralelo)
    tiene_subcarpetas = carpeta.hijas.exists()
    tiene_archivos = carpeta.archivos.exists()

    if request.method == "POST":
        # Recalcular en POST por seguridad
        tiene_subcarpetas = carpeta.hijas.exists()
        tiene_archivos = carpeta.archivos.exists()

        if tiene_subcarpetas or tiene_archivos:
            messages.error(
                request,
                "No se puede eliminar la carpeta porque contiene subcarpetas o archivos.",
            )
            fallback_url = reverse("archivos:carpeta_eliminar", kwargs={"pk": carpeta.pk})
            return redirect_next(request, fallback_url)

        parent = carpeta.parent
        nombre = carpeta.nombre
        carpeta.delete()
        messages.success(request, f"Carpeta «{nombre}» eliminada correctamente.")

        if parent:
            fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": parent.pk})
        else:
            fallback_url = reverse("archivos:explorador_raiz")

        return redirect_next(request, fallback_url)

    # Cancel vuelve al sitio “natural” + conserva next si venías de tabla/lista
    cancel_url_base = (
        reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.parent.pk})
        if carpeta.parent
        else reverse("archivos:explorador_raiz")
    )
    cancel_url = with_next(cancel_url_base, request)

    return render(
        request,
        "archivos/carpeta_eliminar_confirm.html",
        {
            "carpeta": carpeta,
            "tiene_subcarpetas": tiene_subcarpetas,
            "tiene_archivos": tiene_archivos,
            "cancel_url": cancel_url,
        },
    )

@login_required
def archivo_eliminar(request, pk):
    """
    Eliminar un archivo concreto.
    Respeta ?next=... para volver a la vista de origen (tabla/lista/carpeta).
    """
    archivo = get_object_or_404(Archivo, pk=pk)
    carpeta = archivo.carpeta

    if not carpeta.puede_escribir(request.user):
        return HttpResponseForbidden("No tienes permisos para eliminar archivos aquí.")

    # ¿A dónde volver si no hay next?
    fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})

    if request.method == "POST":
        nombre = archivo.nombre_original
        archivo.delete()
        messages.success(request, f"Archivo «{nombre}» eliminado correctamente.")
        return redirect_next(request, fallback_url)

    cancel_url = with_next(fallback_url, request)

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
@login_required
def eliminar_archivos_masivo(request, pk):
    carpeta = get_object_or_404(Carpeta, pk=pk)

    if not carpeta.puede_escribir(request.user):
        return JsonResponse({"ok": False, "error": "Sin permisos"}, status=403)

    ids = request.POST.getlist("ids")
    if not ids:
        return JsonResponse({"ok": False, "error": "No hay elementos seleccionados"}, status=400)

    qs = Archivo.objects.filter(pk__in=ids, carpeta=carpeta)
    deleted = qs.count()
    qs.delete()

    return JsonResponse({"ok": True, "deleted": deleted})

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
    """
    Renombrar un archivo (solo el nombre lógico, no el fichero físico).
    """
    archivo = get_object_or_404(Archivo, pk=pk)
    carpeta = archivo.carpeta

    # Permiso básico: superuser, staff o owner de la carpeta
    if not (request.user.is_superuser or request.user.is_staff or carpeta.owner == request.user):
        return HttpResponseForbidden("No tienes permisos para renombrar este archivo.")

    form_url = reverse("archivos:archivo_renombrar", kwargs={"pk": archivo.pk})

    if request.method == "POST":
        nuevo_nombre = request.POST.get("nombre_original", "").strip()

        if not nuevo_nombre:
            messages.error(request, "El nombre no puede estar vacío.")
            return redirect_next(request, form_url)

        archivo.nombre_original = nuevo_nombre
        archivo.save()
        messages.success(request, "Archivo renombrado correctamente.")
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
        return redirect_next(request, fallback_url)

    cancel_url_base = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.pk})
    cancel_url = with_next(cancel_url_base, request)

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
    archivo = get_object_or_404(Archivo, pk=pk)
    carpeta_origen = archivo.carpeta

    # Permiso básico para mover: superuser/staff o owner de la carpeta origen
    if not (request.user.is_superuser or request.user.is_staff or carpeta_origen.owner == request.user):
        return HttpResponseForbidden("No tienes permisos para mover este archivo.")

    # Carpetas destino "permitidas":
    # - superuser/staff: todas
    # - si no: carpetas donde eres owner
    if request.user.is_superuser or request.user.is_staff:
        carpetas_destino = Carpeta.objects.all().order_by("nombre")
    else:
        carpetas_destino = Carpeta.objects.filter(owner=request.user).order_by("nombre")

    # Excluir la carpeta actual
    carpetas_destino = carpetas_destino.exclude(pk=carpeta_origen.pk)

    # URL del formulario (para reintentar sin perder next)
    form_url = reverse("archivos:archivo_mover", kwargs={"pk": archivo.pk})

    if request.method == "POST":
        destino_id = (request.POST.get("carpeta_destino") or "").strip()

        if not destino_id.isdigit():
            messages.error(request, "Selecciona una carpeta destino válida.")
            return redirect_next(request, form_url)

        carpeta_destino = get_object_or_404(Carpeta, pk=int(destino_id))

        # Revalidar permiso sobre destino
        if not (request.user.is_superuser or request.user.is_staff or carpeta_destino.owner == request.user):
            return HttpResponseForbidden("No tienes permisos para mover a esa carpeta.")

        # Evitar mover a la misma carpeta (por si alguien manipula el POST)
        if carpeta_destino.pk == carpeta_origen.pk:
            messages.warning(request, "El archivo ya está en esa carpeta.")
            fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_origen.pk})
            return redirect_next(request, fallback_url)

        archivo.carpeta = carpeta_destino
        archivo.save()
        messages.success(request, f"Archivo movido a «{carpeta_destino.nombre}».")
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_destino.pk})
        return redirect_next(request, fallback_url)

    # Cancelar: volver al origen manteniendo next
    cancel_url_base = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_origen.pk})
    cancel_url = with_next(cancel_url_base, request)

    return render(
        request,
        "archivos/archivo_mover.html",
        {
            "archivo": archivo,
            "carpeta_origen": carpeta_origen,
            "carpetas_destino": carpetas_destino,
            "cancel_url": cancel_url,
        },
    )

@login_required
def carpeta_mover(request, pk):
    carpeta = get_object_or_404(Carpeta, pk=pk)

    # Permiso básico
    if not (request.user.is_superuser or request.user.is_staff or carpeta.owner == request.user):
        return HttpResponseForbidden("No tienes permisos para mover esta carpeta.")

    # Carpetas destino posibles
    if request.user.is_superuser or request.user.is_staff:
        carpetas_destino = Carpeta.objects.exclude(pk=carpeta.pk)
    else:
        carpetas_destino = Carpeta.objects.filter(owner=request.user).exclude(pk=carpeta.pk)

    # Excluir hijas (y subhijas) para evitar bucles
    carpetas_destino = [
        c for c in carpetas_destino
        if not carpeta.es_ancestro_de(c)
    ]

    if request.method == "POST":
        destino_id = (request.POST.get("carpeta_destino") or "").strip()

        if destino_id == "":
            messages.error(request, "Selecciona una carpeta destino.")
            fallback_url = reverse("archivos:carpeta_mover", kwargs={"pk": carpeta.pk})
            return redirect_next(request, fallback_url)

        if destino_id == "ROOT":
            carpeta.parent = None
            carpeta.save()
            messages.success(request, "Carpeta movida a nivel raíz.")
            #return redirect("archivos:explorador_raiz")
            fallback_url = reverse("archivos:explorador_raiz")
            return redirect_next(request, fallback_url)

        if not destino_id.isdigit():
            messages.error(request, "Destino no válido.")
            fallback_url = reverse("archivos:carpeta_mover", kwargs={"pk": carpeta.pk})
            return redirect_next(request, fallback_url)

        carpeta_destino = get_object_or_404(Carpeta, pk=int(destino_id))

        # Seguridad extra
        if carpeta_destino.pk == carpeta.pk or carpeta.es_ancestro_de(carpeta_destino):
            messages.error(request, "No se puede mover una carpeta dentro de sí misma.")
            fallback_url = reverse("archivos:carpeta_mover", kwargs={"pk": carpeta.pk})
            return redirect_next(request, fallback_url)

        carpeta.parent = carpeta_destino
        carpeta.save()
        messages.success(request, f"Carpeta movida a «{carpeta_destino.get_ruta_display}».")
        #return redirect("archivos:explorador_carpeta", pk=carpeta_destino.pk)
        fallback_url = reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta_destino.pk})
        return redirect_next(request, fallback_url)

    cancel_url_base = (
        reverse("archivos:explorador_carpeta", kwargs={"pk": carpeta.parent.pk})
        if carpeta.parent
        else reverse("archivos:explorador_raiz")
    )
    cancel_url = with_next(cancel_url_base, request)

    return render(
        request,
        "archivos/carpeta_mover.html",
        {
            "carpeta": carpeta,
            "carpetas_destino": carpetas_destino,
            "cancel_url": cancel_url,
        },
    )


@require_POST
@login_required
def subir_carpeta(request, pk):
    carpeta_base = get_object_or_404(Carpeta, pk=pk)

    if not carpeta_base.puede_escribir(request.user):
        return JsonResponse({"ok": False, "error": "Sin permisos"}, status=403)

    files = request.FILES.getlist("files")
    relpaths = request.POST.getlist("relpath")
    keep_root = request.POST.get("keep_root") in ("1", "true", "True", "yes", "on")

    if not files:
        return JsonResponse({"ok": False, "error": "No hay archivos"}, status=400)
    if len(relpaths) != len(files):
        return JsonResponse({"ok": False, "error": "Datos incompletos"}, status=400)

    created = 0
    created_folders = 0
    cache = {}

    def get_or_create_child(parent: Carpeta, name: str) -> Carpeta:
        nonlocal created_folders
        key = (parent.pk, name)
        if key in cache:
            return cache[key]

        obj, was_created = Carpeta.objects.get_or_create(
            parent=parent,
            nombre=name,
            defaults={
                "owner": request.user,
                "visibilidad": parent.visibilidad,
                "departamento": getattr(parent, "departamento", None),
            },
        )
        if was_created:
            created_folders += 1
        cache[key] = obj
        return obj

    for f, rp in zip(files, relpaths):
        p = PurePosixPath(rp)
        parts = [x for x in p.parts if x not in ("", ".", "..")]

        # si NO queremos conservar la carpeta raíz, la eliminamos
        if not keep_root and len(parts) > 1:
            parts = parts[1:]

        # si por lo que sea llega solo "archivo.ext"
        if len(parts) == 1:
            folders, filename = [], parts[0]
            current = carpeta_base
        else:
            # si keep_root=True, el primer elemento es la carpeta raíz que queremos crear
            folders, filename = parts[:-1], parts[-1]
            current = carpeta_base

            # crea todos los niveles (incluye la raíz si keep_root=True)
            for folder_name in folders:
                current = get_or_create_child(current, folder_name)

        Archivo.objects.create(
            carpeta=current,
            fichero=f,
            nombre_original=f.name,
            descripcion="",
            subido_por=request.user,
        )
        created += 1

    return JsonResponse({"ok": True, "files": created, "folders": created_folders})
    
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
        return (carpeta.owner_id == user.id) or user.is_superuser or user.is_staff

    if carpeta.visibilidad == "DEPTO":
        return user.groups.filter(id=carpeta.departamento_id).exists() or user.is_superuser or user.is_staff

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
def file_preview(request, file_id: int):
    a = get_object_or_404(Archivo, pk=file_id)

    if not _can_access_file(request.user, a):
        raise Http404()

    if not a.fichero:
        raise Http404("Archivo sin fichero asociado")

    content_type = _guess_content_type(a)

    # Abrimos el fichero desde el storage de Django
    fh = a.fichero.open("rb")
    resp = FileResponse(fh, content_type=content_type)

    filename = (a.nombre_original or "archivo").replace('"', "")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'

    return resp

@login_required
def file_download(request, file_id: int):
    a = get_object_or_404(Archivo, pk=file_id)

    if not _can_access_file(request.user, a):
        raise Http404()

    if not a.fichero:
        raise Http404("Archivo sin fichero asociado")

    fh = a.fichero.open("rb")
    resp = FileResponse(fh, content_type="application/octet-stream")

    filename = (a.nombre_original or "archivo").replace('"', "")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'

    return resp