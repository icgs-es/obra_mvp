from django.urls import path
from . import views

app_name = "archivos"

urlpatterns = [
    path("", views.explorador_raiz, name="explorador_raiz"),
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
]
