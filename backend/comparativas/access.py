from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def comparativas_access_required(view_func):
    """
    Puente de compatibilidad.

    PORTAL INTASA:
      - gestion.access_gestion

    Módulo independiente / ORDIX:
      - comparativas.access_comparativas
    """

    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user

        if (
            user.is_superuser
            or user.has_perm(
                "comparativas.access_comparativas"
            )
            or user.has_perm(
                "gestion.access_gestion"
            )
        ):
            return view_func(
                request,
                *args,
                **kwargs,
            )

        raise PermissionDenied

    return wrapped
