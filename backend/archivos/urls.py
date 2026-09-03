from django.urls import path
from . import views
from . import cloud_views
from . import cloud_actions
from . import media_views
from . import cloud_folder_upload_views

app_name = "archivos"

urlpatterns = [
    path(
        "archivo/<int:file_id>/media/",
        media_views.media_stream,
        name="media_stream",
    ),
    path("", cloud_views.cloud_explorer, name="explorador_raiz"),
    path("cloud/abrir/", cloud_views.cloud_file_open, name="cloud_file_open"),
    path(
        "cloud/carpeta/nueva/",
        cloud_views.cloud_folder_create,
        name="cloud_folder_create",
    ),
    path(
        "cloud/subir/",
        cloud_views.cloud_upload_files,
        name="cloud_upload_files",
    ),
    path(
        "cloud/folder-upload/preflight/",
        cloud_folder_upload_views.cloud_folder_upload_preflight,
        name="cloud_folder_upload_preflight",
    ),
    path(
        "cloud/folder-upload/execute/",
        cloud_folder_upload_views.cloud_folder_upload_execute,
        name="cloud_folder_upload_execute",
    ),
    path(
        "cloud/renombrar/",
        cloud_actions.cloud_item_rename,
        name="cloud_item_rename",
    ),
    path(
        "cloud/mover/",
        cloud_actions.cloud_item_move,
        name="cloud_item_move",
    ),
    path(
        "cloud/eliminar/",
        cloud_actions.cloud_item_delete,
        name="cloud_item_delete",
    ),
    path("carpeta/<int:pk>/", views.explorador_carpeta, name="explorador_carpeta"),
    path("carpeta/<int:pk>/subir/", views.subir_archivo, name="subir_archivo"),
    
    # 🔽 NUEVO
    path("carpetas/nueva/", views.carpeta_raiz_create, name="carpeta_raiz_create"),
    path("carpetas/<int:carpeta_id>/nueva/", views.subcarpeta_create, name="subcarpeta_create"),
    
     # 🔽 NUEVO: gestión de carpetas
    path("carpeta/<int:pk>/renombrar/", views.carpeta_renombrar, name="carpeta_renombrar"),
    path("carpeta/<int:pk>/eliminar/", views.carpeta_eliminar, name="carpeta_eliminar"),
    path("carpeta/<int:pk>/mover/", views.carpeta_mover, name="carpeta_mover"),
    
    # 🔽 NUEVO: gestión de archivos
    path("archivo/<int:pk>/eliminar/", views.archivo_eliminar, name="archivo_eliminar"),
    path("archivo/<int:pk>/detalle/", views.archivo_detalle, name="archivo_detalle"),
    path("archivo/<int:pk>/renombrar/", views.archivo_renombrar, name="archivo_renombrar"),
    path("archivo/<int:pk>/mover/", views.archivo_mover, name="archivo_mover"),

    path("f/<int:file_id>/preview/", views.file_preview, name="preview"),
    path("f/<int:file_id>/download/", views.file_download, name="download"),
    
    path("carpeta/<int:pk>/subir-carpeta/", views.subir_carpeta, name="subir_carpeta"),
    path("carpeta/<int:pk>/eliminar-masivo/", views.eliminar_archivos_masivo, name="eliminar_archivos_masivo"),
    
    path(
        "archivo/<int:file_id>/editar-online/",
        views.archivo_editar_online,
        name="archivo_editar_online",
    ),
    path("archivo/<int:file_id>/descargar/", views.archivo_descargar, name="archivo_descargar"),

]
