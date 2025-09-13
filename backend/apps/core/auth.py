from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.views import redirect_to_login

ALLOWED_GROUPS = {
    "Administrador",
    "Gerencia",
    "Constructora",
    "Responsable Constructora",
}

def user_has_constructora_access(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=ALLOWED_GROUPS).exists()

def require_constructora(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # respeta next=/manual/...
            return redirect_to_login(request.get_full_path())
        if not user_has_constructora_access(request.user):
            return HttpResponseForbidden("No tiene permisos para acceder al módulo Constructora.")
        return view_func(request, *args, **kwargs)
    return _wrapped
