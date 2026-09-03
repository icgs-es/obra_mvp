from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def informes_index(request):
    """
    Centro centralizado de informes del Portal INTASA.
    No duplica lógica: enlaza informes existentes y deja preparada
    la evolución hacia informes formales nuevos.
    """
    informes = [
        {
            "grupo": "Planificación / Producción",
            "items": [
                {
                    "titulo": "Producción / asignación de personal",
                    "descripcion": "Listado formal de asignaciones y producción de personal por fechas, obra, vivienda, capítulo y partida.",
                    "url": "/app/planificacion-obra/asignaciones/informe/",
                    "icono": "bi-person-workspace",
                    "estado": "Disponible",
                },
                {
                    "titulo": "Planificación de obra",
                    "descripcion": "Informe ejecutivo de planificación, tareas, previsto, real y desviaciones. Pendiente de formalizar como informe separado.",
                    "url": "/app/planificacion-obra/planning/",
                    "icono": "bi-kanban",
                    "estado": "Operativo",
                },
                {
                    "titulo": "Producción por vivienda",
                    "descripcion": "Informe específico de producción por vivienda: personal, horas, coste, materiales y partidas. Próximo informe formal.",
                    "url": "",
                    "icono": "bi-house-check",
                    "estado": "Próximo",
                },
            ],
        },
        {
            "grupo": "Gestión",
            "items": [
                {
                    "titulo": "Albaranes de proveedores",
                    "descripcion": "Informe de albaranes con filtros por empresa, proveedor, asignación, auditoría, PDF, fechas e importes.",
                    "url": "/app/gestion/albaranes/informe/",
                    "icono": "bi-truck",
                    "estado": "Disponible",
                },
                {
                    "titulo": "Facturas de proveedores",
                    "descripcion": "Informe de facturas con filtros por empresa, proveedor, auditoría, estado, fechas, pago e importes.",
                    "url": "/app/gestion/facturas/informe/",
                    "icono": "bi-file-earmark-text",
                    "estado": "Disponible",
                },
                {
                    "titulo": "Compras / proveedores",
                    "descripcion": "Informe agregado de compras por proveedor, recurso, obra y periodo. Pendiente.",
                    "url": "",
                    "icono": "bi-basket",
                    "estado": "Próximo",
                },
            ],
        },
        {
            "grupo": "Control económico",
            "items": [
                {
                    "titulo": "Coste por vivienda",
                    "descripcion": "Resumen de coste real por vivienda, partida, capítulo y desviación contra previsto. Pendiente.",
                    "url": "",
                    "icono": "bi-cash-coin",
                    "estado": "Próximo",
                },
                {
                    "titulo": "Desviaciones previsto vs real",
                    "descripcion": "Informe de desviaciones por obra, vivienda, capítulo, partida y recurso. Pendiente.",
                    "url": "",
                    "icono": "bi-graph-down-arrow",
                    "estado": "Próximo",
                },
                {
                    "titulo": "Materiales por vivienda",
                    "descripcion": "Consumos y materiales imputados por vivienda, partida y proveedor. Pendiente.",
                    "url": "",
                    "icono": "bi-box-seam",
                    "estado": "Próximo",
                },
            ],
        },
    ]

    # RBAC_GESTION_INFORMES_FILTER_V1
    puede_ver_gestion = (
        request.user.is_superuser
        or request.user.has_perm(
            "gestion.access_gestion"
        )
    )

    if not puede_ver_gestion:
        informes = [
            grupo
            for grupo in informes
            if grupo.get("grupo")
            not in {
                "Gestión",
                "Control económico",
            }
        ]

    return render(
        request,
        "informes/index.html",
        {
            "informes": informes,
            "puede_ver_gestion": (
                puede_ver_gestion
            ),
        },
    )
