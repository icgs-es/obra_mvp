from django.urls import path

from . import views


app_name = "comparativas"


urlpatterns = [
    path(
        "",
        views.comparativas_list,
        name="list",
    ),
    path(
        "nueva/",
        views.comparativa_create,
        name="create",
    ),
    # COMPARATIVAS_EDITAR_EXPEDIENTE_V1
    path(
        "<uuid:uid>/editar/",
        views.comparativa_update,
        name="update",
    ),
    # COMPARATIVAS_PRESUPUESTO_DOCUMENT_PREVIEW_V1
    path(
        "<uuid:uid>/importar-presupuesto/ver/",
        views.presupuesto_import_document,
        name="presupuesto_import_document",
    ),
    # COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1
    path(
        "<uuid:uid>/importar-presupuesto/",
        views.presupuesto_import,
        name="presupuesto_import",
    ),
    # COMPARATIVAS_V2D_EXECUTIVE_IA_V1
    path(
        "<uuid:uid>/comparativa-ia/",
        views.comparativa_executive_ia,
        name="executive_ia",
    ),
    path(
        "<uuid:uid>/",
        views.comparativa_detail,
        name="detail",
    ),
    path(
        "<uuid:uid>/ofertantes/nuevo/",
        views.ofertante_create,
        name="ofertante_create",
    ),
    path(
        "ofertantes/<int:pk>/ofertas/nueva/",
        views.oferta_create,
        name="oferta_create",
    ),
    path(
        "ofertas/<int:pk>/eliminar/",
        views.oferta_delete,
        name="oferta_delete",
    ),
    path(
        "ofertas/<int:pk>/documentos/subir/",
        views.documento_upload,
        name="documento_upload",
    ),
    # COMPARATIVAS_V2C_EDIT_CONFIRMED_CONCEPTS_R1
    path(
        "documentos/<int:pk>/conceptos/editar/",
        views.documento_conceptos_editar,
        name="documento_conceptos_editar",
    ),
    # COMPARATIVAS_V2C_PREVIEW_CONFIRM_R1
    path(
        "documentos/<int:pk>/conceptos/",
        views.documento_conceptos,
        name="documento_conceptos",
    ),
    path(
        "documentos/<int:pk>/ver/",
        views.documento_view,
        name="documento_view",
    ),
    path(
        "documentos/<int:pk>/inteligencia/",
        views.documento_intelligence,
        name="documento_intelligence",
    ),
]
