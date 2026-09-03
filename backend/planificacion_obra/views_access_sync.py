from __future__ import annotations

import json
import traceback
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render


IMPORTS_ROOT = Path('/app/imports')
REPORT_ROOT = Path('/tmp/planificacion_sync_inspect')
DEFAULT_TEAM = 'INVERADRIDE'


def _is_allowed_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _safe_import_folder(raw_folder: str) -> Path:
    folder = Path(raw_folder).resolve()
    root = IMPORTS_ROOT.resolve()

    if not str(folder).startswith(str(root)):
        raise ValueError('Carpeta no permitida')

    if not folder.exists() or not folder.is_dir():
        raise ValueError('La carpeta no existe')

    return folder


def _folder_has_required_planning_files(folder: Path) -> bool:
    required = [
        'tblPartida.xlsx',
        'tblTareas.xlsx',
        'tblTareasRecursos.xlsx',
        'tblTareasRecursosInicial.xlsx',
        'tblRecursos.xlsx',
        'tblRecursoAlmacen.xlsx',
    ]
    return all((folder / name).exists() for name in required)


def _list_access_sync_folders():
    if not IMPORTS_ROOT.exists():
        return []

    folders = []

    for p in IMPORTS_ROOT.iterdir():
        if p.is_dir() and (p.name.startswith('access_sync') or p.name == 'access'):
            folders.append(p)

    folders = sorted(set(folders), key=lambda x: x.stat().st_mtime, reverse=True)

    data = []
    for p in folders:
        valid = _folder_has_required_planning_files(p)
        data.append({
            'path': str(p),
            'name': p.name,
            'mtime': datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            'planning_valid': valid,
            'label': f"{p} · {'OK planificación' if valid else 'faltan tablas planificación'}",
        })

    return data


def _default_planning_folder(folders):
    for folder in folders:
        if folder.get('planning_valid'):
            return folder['path']
    return folders[0]['path'] if folders else ''


def _required_files_status(folder: Path):
    required = [
        'tblPartida.xlsx',
        'tblTareas.xlsx',
        'tblTareasRecursos.xlsx',
        'tblTareasRecursosInicial.xlsx',
        'tblRecursos.xlsx',
        'tblRecursoAlmacen.xlsx',
    ]

    status = []

    for name in required:
        p = folder / name
        status.append({
            'name': name,
            'exists': p.exists(),
            'size': p.stat().st_size if p.exists() else 0,
        })

    return status


def _latest_file(folder: Path, pattern: str):
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    p = files[0]
    return {
        'path': str(p),
        'name': p.name,
        'mtime': datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
        'size': p.stat().st_size,
    }


def _planning_counts(team_name: str):
    try:
        Team = apps.get_model('usuarios', 'Team')
        team = Team.objects.filter(name=team_name).first()
        if not team:
            return []
    except Exception:
        return []

    names = [
        ('RecursoCatalogo', 'Recursos catálogo'),
        ('TareaObra', 'Tareas'),
        ('TareaRecursoPrevisto', 'Recursos previstos'),
        ('TareaRecursoReal', 'Recursos reales'),
        ('RecursoAlmacenMovimiento', 'Movimientos almacén'),
    ]

    cards = []

    for model_name, label in names:
        try:
            model = apps.get_model('planificacion_obra', model_name)
            value = model.objects.filter(team=team).count()
        except Exception:
            value = '—'

        cards.append({
            'label': label,
            'value': value,
            'hint': model_name,
        })

    return cards


def _load_report(path: str):
    if not path:
        return {}

    p = Path(path)
    if not p.exists():
        return {}

    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _run_sync_planificacion(folder: Path, team: str, commit: bool):
    missing = [item['name'] for item in _required_files_status(folder) if not item['exists']]
    if missing:
        raise ValueError(
            'La carpeta seleccionada no contiene las tablas de planificación requeridas. '
            'Faltan: ' + ', '.join(missing)
        )

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    mode = 'commit' if commit else 'dry_run'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = REPORT_ROOT / f'web_sync_access_planificacion_{mode}_{ts}.json'

    out = StringIO()

    kwargs = {
        'folder': str(folder),
        'team': team,
        'sample': 20,
        'json_out': str(report_file),
        'stdout': out,
    }

    if commit:
        kwargs['commit'] = True

    call_command('sync_access_planificacion', **kwargs)

    output = out.getvalue()
    report_data = _load_report(str(report_file))

    return {
        'title': 'Sincronización Planificación Access',
        'mode': 'COMMIT' if commit else 'DRY-RUN',
        'success': True,
        'output': output,
        'report_file': str(report_file),
        'report_data': report_data,
        'tables': report_data.get('tables', {}),
        'created': report_data.get('created', {}),
        'backup_dir': report_data.get('backup_dir', ''),
    }


@login_required
def sync_access_planificacion(request):
    if not _is_allowed_user(request.user):
        return HttpResponseForbidden('No tienes permisos para acceder a esta herramienta.')

    folders = _list_access_sync_folders()
    selected_folder = (
        request.POST.get('folder')
        or request.GET.get('folder')
        or _default_planning_folder(folders)
    )
    team = request.POST.get('team') or request.GET.get('team') or DEFAULT_TEAM

    context = {
        'folders': folders,
        'selected_folder': selected_folder,
        'team': team,
        'file_status': [],
        'selected_folder_ready': False,
        'ran': False,
        'action': '',
        'result': None,
        'error': '',
        'sync_cards': _planning_counts(team),
        'latest_dry_report': _latest_file(REPORT_ROOT, 'web_sync_access_planificacion_dry_run_*.json') if REPORT_ROOT.exists() else None,
        'latest_commit_report': _latest_file(REPORT_ROOT, 'web_sync_access_planificacion_commit_*.json') if REPORT_ROOT.exists() else None,
    }

    if selected_folder:
        try:
            folder = _safe_import_folder(selected_folder)
            context['file_status'] = _required_files_status(folder)
            context['selected_folder_ready'] = all(item['exists'] for item in context['file_status'])
        except Exception as exc:
            context['error'] = str(exc)

    if request.method == 'POST':
        action = request.POST.get('action') or 'analyze'
        context['ran'] = True
        context['action'] = action

        try:
            folder = _safe_import_folder(selected_folder)

            if action not in ('analyze', 'commit'):
                raise ValueError('Acción no válida.')

            if action == 'commit':
                if not request.user.is_superuser:
                    return HttpResponseForbidden('Solo superusuarios pueden sincronizar datos reales.')

                if request.POST.get('confirm_commit') != '1':
                    messages.error(request, 'Debes marcar la confirmación antes de sincronizar.')
                    return redirect(f'/app/planificacion-obra/sync-access/?folder={selected_folder}&team={team}')

            context['result'] = _run_sync_planificacion(
                folder=folder,
                team=team,
                commit=(action == 'commit'),
            )

            if action == 'commit':
                messages.success(request, 'Sincronización ejecutada correctamente.')
            else:
                messages.success(request, 'Análisis ejecutado correctamente. No se modificó la base de datos.')

            context['sync_cards'] = _planning_counts(team)

        except Exception as exc:
            if isinstance(exc, ValueError):
                context['error'] = str(exc)
                messages.error(request, str(exc))
            else:
                context['error'] = traceback.format_exc()

    return render(request, 'planificacion_obra/access_sync_verify.html', context)


def access_sync_verify(request):
    return sync_access_planificacion(request)
