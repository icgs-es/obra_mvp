from __future__ import annotations

import json
import re
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Max
from django.http import HttpResponseForbidden
from django.shortcuts import render


IMPORTS_ROOT = Path("/app/imports")
DEFAULT_TEAM = "INVERADRIDE"
DEFAULT_TEAM_ID = 1


def _is_allowed_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _safe_import_folder(raw_folder: str) -> Path:
    folder = Path(raw_folder).resolve()
    root = IMPORTS_ROOT.resolve()

    if not str(folder).startswith(str(root)):
        raise ValueError("Carpeta no permitida")

    if not folder.exists() or not folder.is_dir():
        raise ValueError("La carpeta no existe")

    return folder


def _list_access_sync_folders():
    if not IMPORTS_ROOT.exists():
        return []

    folders = []

    for p in IMPORTS_ROOT.iterdir():
        if p.is_dir() and p.name.startswith("access_sync"):
            folders.append(p)

    nested = IMPORTS_ROOT / "access_sync"
    if nested.exists():
        for p in nested.iterdir():
            if p.is_dir() and p.name.startswith("access_sync"):
                folders.append(p)

    folders = sorted(set(folders), key=lambda x: x.stat().st_mtime, reverse=True)

    return [
        {
            "path": str(p),
            "name": p.name,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
        for p in folders
    ]


def _required_files_status(folder: Path):
    required = [
        "tblPartida.xlsx",
        "tblTareas.xlsx",
        "tblTareasRecursos.xlsx",
        "tblTareasRecursosInicial.xlsx",
        "tblRecursos.xlsx",
        "tblRecursoAlmacen.xlsx",
    ]

    status = []

    for name in required:
        p = folder / name
        status.append(
            {
                "name": name,
                "exists": p.exists(),
                "size": p.stat().st_size if p.exists() else 0,
            }
        )

    return status


def _latest_file(folder: Path, pattern: str):
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    p = files[0]
    return {
        "path": str(p),
        "name": p.name,
        "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "size": p.stat().st_size,
    }


def _run_partidas_tareas(folder: Path, team: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = folder / f"web_sync_access_partidas_tareas_{ts}.json"

    out = StringIO()

    call_command(
        "sync_access_partidas_tareas",
        folder=str(folder),
        team=team,
        sample=20,
        json_out=str(report_file),
        stdout=out,
    )

    stats = {}
    samples = {}

    if report_file.exists():
        data = json.loads(report_file.read_text(encoding="utf-8"))
        stats = data.get("stats", {})
        samples = data.get("samples", {})

    return {
        "title": "Partidas + Tareas",
        "success": True,
        "output": out.getvalue(),
        "report_file": str(report_file),
        "stats": stats,
        "samples": samples,
    }


def _parse_reales_stats(output: str):
    wanted = {
        "Filas leídas": "filas_leidas",
        "Crear": "crear",
        "Actualizar": "actualizar",
        "Sin cambios": "sin_cambios",
        "Sin IdRecursoTarea": "sin_id_recurso_tarea",
        "Sin tarea enlazada": "sin_tarea_enlazada",
        "Sin unidad enlazada": "sin_unidad_enlazada",
        "Sin partida enlazada": "sin_partida_enlazada",
        "Con empleado enlazado": "con_empleado_enlazado",
        "Con recurso catálogo enlazado": "con_recurso_catalogo_enlazado",
        "Sin empleado ni recurso catálogo": "sin_empleado_ni_recurso",
        "Con movimiento almacén enlazado": "con_movimiento_almacen",
        "Sin movimiento almacén cuando viene informado": "sin_movimiento_almacen_informado",
    }

    stats = {}

    for line in output.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()

        if ":" not in clean:
            continue

        key, value = clean.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key in wanted:
            try:
                stats[wanted[key]] = int(value)
            except Exception:
                stats[wanted[key]] = value

    return stats


def _run_recursos_reales(folder: Path, team_id: int):
    out = StringIO()

    call_command(
        "import_access_tareas_recursos_reales_planificacion",
        str(folder),
        team_id=team_id,
        stdout=out,
    )

    output = out.getvalue()

    return {
        "title": "Recursos reales / TareasRecursos",
        "success": True,
        "output": output,
        "report_file": "",
        "stats": _parse_reales_stats(output),
        "samples": {},
    }


def _field_is_text(model, field_name: str) -> bool:
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return False
    return field.get_internal_type() in ("CharField", "TextField")


def _build_sync_status(folders, selected_folder: str, latest_partidas_report=None, latest_apply_command: str = ""):
    latest_folder = folders[0] if folders else None

    try:
        TareaObra = apps.get_model("planificacion_obra", "TareaObra")
        qs_tareas = TareaObra.objects.exclude(legacy_key__isnull=True)
        if _field_is_text(TareaObra, "legacy_key"):
            qs_tareas = qs_tareas.exclude(legacy_key="")
        tareas_legacy_count = qs_tareas.count()
    except Exception:
        tareas_legacy_count = "—"

    try:
        TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
        qs_reales = TareaRecursoReal.objects.filter(legacy_id_recurso_tarea__lt=300000)
        reales_legacy_count = qs_reales.count()
        ultimo_legacy_id = qs_reales.aggregate(value=Max("legacy_id_recurso_tarea")).get("value") or "—"
    except Exception:
        reales_legacy_count = "—"
        ultimo_legacy_id = "—"

    try:
        PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")
        partidas_count = PartidaCatalogo.objects.count()
    except Exception:
        partidas_count = "—"

    return {
        "cards": [
            {"label": "Tareas Access", "value": tareas_legacy_count, "hint": "TareaObra con legacy_key"},
            {"label": "Recursos reales", "value": reales_legacy_count, "hint": "legacy_id_recurso_tarea < 300000"},
            {"label": "Último recurso", "value": ultimo_legacy_id, "hint": "Máximo legacy_id importado"},
            {"label": "Partidas", "value": partidas_count, "hint": "PartidaCatalogo total"},
        ],
        "latest_folder": latest_folder,
        "selected_folder": selected_folder,
        "latest_report": latest_partidas_report,
        "apply_command": latest_apply_command,
    }


@login_required
def access_sync_verify(request):
    if not _is_allowed_user(request.user):
        return HttpResponseForbidden("No tienes permisos para acceder a esta herramienta.")

    folders = _list_access_sync_folders()
    selected_folder = request.POST.get("folder") or request.GET.get("folder") or (folders[0]["path"] if folders else "")
    team = request.POST.get("team") or request.GET.get("team") or DEFAULT_TEAM

    try:
        team_id = int(request.POST.get("team_id") or request.GET.get("team_id") or DEFAULT_TEAM_ID)
    except Exception:
        team_id = DEFAULT_TEAM_ID

    context = {
        "folders": folders,
        "selected_folder": selected_folder,
        "team": team,
        "team_id": team_id,
        "file_status": [],
        "ran": False,
        "action": "",
        "results": [],
        "error": "",
        "latest_partidas_report": None,
        "latest_apply_command": "",
    }

    folder = None

    if selected_folder:
        try:
            folder = _safe_import_folder(selected_folder)
            context["file_status"] = _required_files_status(folder)
            context["latest_partidas_report"] = _latest_file(folder, "*sync_access_partidas_tareas*.json")
            context["latest_apply_command"] = f"cd /opt/obra_mvp/infra && ./sync_access_obras.sh --folder {folder} --apply"
        except Exception as exc:
            context["error"] = str(exc)

    if request.method == "POST":
        action = request.POST.get("action") or "dry_run_full"
        context["ran"] = True
        context["action"] = action

        try:
            folder = _safe_import_folder(selected_folder)

            if action in ("dry_run_full", "dry_run_partidas_tareas"):
                context["results"].append(_run_partidas_tareas(folder, team))

            if action in ("dry_run_full", "dry_run_recursos_reales"):
                context["results"].append(_run_recursos_reales(folder, team_id))

        except Exception as exc:
            context["error"] = str(exc)

    context["sync_status"] = _build_sync_status(
        folders=folders,
        selected_folder=selected_folder,
        latest_partidas_report=context["latest_partidas_report"],
        latest_apply_command=context["latest_apply_command"],
    )

    return render(request, "planificacion_obra/access_sync_verify.html", context)
