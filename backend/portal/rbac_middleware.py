# PORTAL INTASA · RBAC_CRM_ACTIVOS_ACCESS_V1


class PortalModuleAccessMiddleware:
    """
    Puertas de entrada RBAC para módulos del Portal.

    La pertenencia a un Team limita datos, pero no concede acceso
    al módulo.

    Excepción:
    /app/crm/set-active-team/ es una utilidad global del Portal
    utilizada por el selector de empresa y no pertenece al
    perímetro funcional del CRM.
    """

    CRM_PERMISSION = "crm.access_crm"
    ACTIVOS_PERMISSION = "activos.access_activos"

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def required_permission(path):
        if (
            path == "/app/crm"
            or path.startswith("/app/crm/")
        ):
            if path.startswith(
                "/app/crm/set-active-team/"
            ):
                return None

            return (
                PortalModuleAccessMiddleware
                .CRM_PERMISSION
            )

        if (
            path == "/activos"
            or path.startswith("/activos/")
        ):
            return (
                PortalModuleAccessMiddleware
                .ACTIVOS_PERMISSION
            )

        return None

    def __call__(self, request):
        user = getattr(request, "user", None)

        if not (
            user is not None
            and getattr(
                user,
                "is_authenticated",
                False,
            )
        ):
            return self.get_response(request)

        path = (
            getattr(request, "path_info", "")
            or ""
        )

        permission = self.required_permission(
            path
        )

        if (
            permission
            and not getattr(
                user,
                "is_superuser",
                False,
            )
            and not user.has_perm(permission)
        ):
            from django.core.exceptions import (
                PermissionDenied,
            )

            raise PermissionDenied(
                "No tiene autorización para "
                "acceder a este módulo."
            )

        return self.get_response(request)
