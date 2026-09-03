# PORTAL INTASA · GESTION_DEFAULT_TODAS_EMPRESAS_MIDDLEWARE_V1

class GestionDefaultTodasEmpresasMiddleware:
    """
    Al iniciar sesión, deja Gestión en modo TODAS MIS EMPRESAS.

    No pisa cambios manuales posteriores dentro de la misma sesión:
    - primera petición autenticada de la sesión => active_team_id = "all"
    - si el usuario luego elige una empresa concreta, se respeta
    """

    SESSION_MARKER = "_gestion_default_todas_empresas_user_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and getattr(user, "is_authenticated", False):
            user_id = str(getattr(user, "pk", "") or "")
            applied_to = str(request.session.get(self.SESSION_MARKER) or "")

            if user_id and applied_to != user_id:
                request.session["active_team_id"] = "all"
                request.session[self.SESSION_MARKER] = user_id
                request.session.modified = True

        return self.get_response(request)



# ============================================================
# RBAC_GESTION_ACCESS_MIDDLEWARE_V1
# Cierra todo el perímetro web de Gestión.
# Team limita datos, pero nunca concede acceso al módulo.
# ============================================================

class GestionAccessMiddleware:
    PERMISSION = "gestion.access_gestion"
    PATH_ROOT = "/app/gestion"
    PATH_PREFIX = "/app/gestion/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (
            getattr(request, "path_info", "")
            or ""
        )

        es_gestion = (
            path == self.PATH_ROOT
            or path.startswith(self.PATH_PREFIX)
        )

        if es_gestion:
            user = getattr(request, "user", None)

            # Los usuarios anónimos continúan hasta @login_required,
            # que mantiene el comportamiento normal de redirección.
            if (
                user is not None
                and getattr(
                    user,
                    "is_authenticated",
                    False,
                )
            ):
                autorizado = (
                    getattr(
                        user,
                        "is_superuser",
                        False,
                    )
                    or user.has_perm(
                        self.PERMISSION
                    )
                )

                if not autorizado:
                    from django.core.exceptions import (
                        PermissionDenied,
                    )

                    raise PermissionDenied(
                        "No tiene autorización para "
                        "acceder al módulo Gestión."
                    )

        return self.get_response(request)
