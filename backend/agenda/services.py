from django.db import models
from django.contrib.auth.models import Group
from django.utils import timezone

ADMIN_GROUPS = {"Administrador", "Gerencia"}

def user_is_admin_like(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    names = set(user.groups.values_list("name", flat=True))
    return bool(ADMIN_GROUPS & names)

def _creator_id_safe(obj):
    try:
        return obj.id
    except Exception:
        return None

def user_can_see_event(user, evento):
    """
    Reglas de visibilidad:
    - Admin/Gerencia/superuser: todo.
    - visibilidad == global: todos.
    - visibilidad == privada: creador (si hay created_by) o invitado (asistentes).
    - visibilidad == depto: si comparte 'departamento' (si existe FK),
      o si está invitado como asistente (fallback).
    """
    if user_is_admin_like(user):
        return True

    vis = (evento.visibilidad or "privada").lower()

    if vis == "global":
        return True

    # privada
    if vis == "privada":
        creator = getattr(evento, "created_by", None)
        if creator and _creator_id_safe(creator) == user.id:
            return True
        return evento.asistentes.filter(id=user.id).exists()

    # depto: intenta con FK departamento (opcional)
    if vis == "depto":
        dep = getattr(evento, "departamento", None)  # si no existe, es None
        if dep is not None:
            # El modelo Team/Departamento debería tener members/leads
            try:
                if user in dep.members.all() or user in dep.leads.all():
                    return True
            except Exception:
                pass
        # Fallback: si está invitado, también ve
        return evento.asistentes.filter(id=user.id).exists()

    return False

def events_between_for_user(user, start, end, base_qs):
    """
    Ventana [start, end) y filtro por user_can_see_event.
    """
    qs = base_qs.filter(inicio__lt=end).filter(
        models.Q(fin__gte=start) | models.Q(fin__isnull=True)
    )
    return [e for e in qs.select_related() if user_can_see_event(user, e)]
