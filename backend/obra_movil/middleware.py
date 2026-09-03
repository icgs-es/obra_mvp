from django.shortcuts import redirect


# OBRA_MOVIL_UX0B_USER_REDIRECT_MIDDLEWARE_V1
class ObraMovilUserRedirectMiddleware:
    """
    Redirige usuarios operativos de obra/almacén a Obra móvil cuando entran
    por la portada del portal.

    No afecta a usuarios normales salvo que su username esté en USERNAMES.
    No redirige dentro de /app/obra-movil/ para evitar bucles.
    No bloquea el acceso manual a otros módulos si el usuario navega a una URL concreta.
    """

    USERNAMES = {
        "almacen",
    }

    LANDING_PATHS = {
        "/",
        "/app",
        "/app/",
        "/app/mi-jornada",
        "/app/mi-jornada/",
        "/app/jornada",
        "/app/jornada/",
        "/app/dashboard",
        "/app/dashboard/",
    }

    TARGET = "/app/obra-movil/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and getattr(user, "is_authenticated", False):
            username = ""
            try:
                username = (user.get_username() or "").strip().lower()
            except Exception:
                username = ""

            if username in self.USERNAMES:
                path = request.path or ""
                if path in self.LANDING_PATHS:
                    return redirect(self.TARGET)

        return self.get_response(request)
