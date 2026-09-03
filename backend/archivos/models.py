from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth.models import Group

import mimetypes

User = settings.AUTH_USER_MODEL

# Opciones de visibilidad de carpeta
VISIBILIDAD_CHOICES = (
    ("GLOBAL", "Global (toda la empresa)"),
    ("DEPTO", "Departamento"),
    ("PRIVADA", "Privada / personal"),
)


def archivo_upload_to(instance, filename):
    """
    Ruta física dentro de MEDIA_ROOT donde guardar el archivo.
    Por ahora usamos: archivos/carpeta_<id>/<filename>
    (La jerarquía lógica la lleva el modelo Carpeta, no hace falta
    replicarla 1:1 en el sistema de ficheros)
    """
    carpeta_id = instance.carpeta_id or "sin_carpeta"
    return f"archivos/carpeta_{carpeta_id}/{filename}"


class Carpeta(models.Model):
    """
    Carpeta lógica dentro del sistema de archivos de Intasa Platform.
    Puede estar anidada (parent), tener visibilidad y opcionalmente
    asociarse a un departamento.
    """
    team = models.ForeignKey(
        "usuarios.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carpetas_documentales",
        help_text=(
            "Empresa propietaria del ámbito documental. "
            "Puede quedar vacío para documentación compartida "
            "o todavía no clasificada."
        ),
    )

    nombre = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="hijas",
    )

    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carpetas_propias",
    )

    visibilidad = models.CharField(
        max_length=20,
        choices=VISIBILIDAD_CHOICES,
        default="GLOBAL",
    )

    # De momento usamos un texto libre para departamento; más adelante
    # lo podemos enlazar a un modelo Departamento concreto.
    departamento = models.ForeignKey(
        Group,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="carpetas",
        help_text="Grupo / departamento propietario de la carpeta.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "carpeta"
        verbose_name_plural = "carpetas"
        ordering = ["parent__id", "nombre"]

    def __str__(self):
        return self.get_ruta_display()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre) or "carpeta"
            self.slug = base[:250]
        super().save(*args, **kwargs)

    def get_ruta_display(self):
        """
        Devuelve la ruta lógica tipo: /Obras/Málaga/Planos
        """
        partes = [self.nombre]
        padre = self.parent
        while padre:
            partes.append(padre.nombre)
            padre = padre.parent
        partes.reverse()
        return "/" + "/".join(partes)

        # --- Helpers de permisos ---

    def _user_in_departamento(self, user):
        """
        Devuelve True si el usuario pertenece al grupo/departamento de la carpeta.
        """
        if not self.departamento or not user.is_authenticated:
            return False
        return user.groups.filter(id=self.departamento_id).exists()

    def _user_in_team(self, user):
        if not self.team_id:
            return True
        return user.teams.filter(id=self.team_id).exists()

    def puede_ver(self, user):
        """
        ¿Puede este usuario ver esta carpeta?
        Regla genérica:
        - superuser: todo
        - GLOBAL: todos
        - PRIVADA: owner + staff
        - DEPTO: miembros del grupo + staff
        """
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        if not self._user_in_team(user):
            return False

        if self.visibilidad == "GLOBAL":
            return True

        if self.visibilidad == "PRIVADA":
            return self.owner_id == user.id

        if self.visibilidad == "DEPTO":
            return self._user_in_departamento(user)

        # Por si en el futuro hay más tipos
        return False

    def puede_escribir(self, user):
        """
        ¿Puede este usuario crear subcarpetas o subir archivos en esta carpeta?
        Regla inicial:
        - superuser y staff: siempre
        - PRIVADA: solo owner
        - DEPTO: miembros del grupo + owner
        - GLOBAL: opcional -> de momento solo staff/superuser
        """
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        if not self._user_in_team(user):
            return False

        if self.visibilidad == "PRIVADA":
            return self.owner_id == user.id

        if self.visibilidad == "DEPTO":
            return self.owner_id == user.id or self._user_in_departamento(user)

        # GLOBAL requiere una capacidad documental Django explícita.
        return user.has_perm("archivos.add_archivo") or user.has_perm(
            "archivos.change_carpeta"
        )
    
    def es_ancestro_de(self, otra):
        """
        Devuelve True si esta carpeta es ancestro de 'otra'
        (para evitar mover una carpeta dentro de sus hijas).
        """
        actual = otra.parent
        while actual:
            if actual.pk == self.pk:
                return True
            actual = actual.parent
        return False

class Archivo(models.Model):
    """Archivo almacenado en el sistema.

    Se guarda físicamente en MEDIA_ROOT y se relaciona lógicamente con una
    Carpeta. Puede tener múltiples versiones lógicas (nombre_logico + version).
    """
    team = models.ForeignKey(
        "usuarios.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archivos_documentales",
        help_text=(
            "Empresa a la que pertenece el documento. "
            "No representa al usuario que realizó la operación."
        ),
    )

    carpeta = models.ForeignKey(
        Carpeta,
        on_delete=models.CASCADE,
        related_name="archivos",
    )
    fichero = models.FileField(
        upload_to=archivo_upload_to,
        blank=True,
    )
    nombre_original = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    subido_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archivos_subidos",
    )

    tamano_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    nombre_logico = models.CharField(max_length=255, null=True, blank=True)
    version = models.PositiveIntegerField(default=1)


    # Referencia neutral al proveedor documental.
    # No contiene credenciales ni lógica específica de Nextcloud.
    storage_provider = models.CharField(
        max_length=32,
        default="local",
        db_index=True,
    )

    # Clave opaca interpretada exclusivamente por el StorageProvider.
    storage_key = models.CharField(
        max_length=1024,
        blank=True,
        default="",
    )

    # Identificador opcional asignado por el proveedor.
    storage_object_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    # ETag, version ID, hash o token equivalente del proveedor.
    storage_version = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    mime_type = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "archivo"
        verbose_name_plural = "archivos"
        ordering = ["-created_at"]
        unique_together = ("carpeta", "nombre_logico", "version")

        # P3_FOLDER_UPLOAD_PERMISSION
        permissions = [
            (
                "upload_folder",
                (
                    "Puede subir carpetas completas "
                    "en INTASA Cloud"
                ),
            ),
        ]

    def __str__(self):
        return self.nombre_original

    def save(self, *args, **kwargs):
        # Si no se ha rellenado nombre_original, lo ponemos por defecto
        if self.fichero and not self.nombre_original:
            self.nombre_original = self.fichero.name

        super().save(*args, **kwargs)

        # Actualizamos tamaño después de guardar el fichero
        if self.fichero and (not self.tamano_bytes or self.tamano_bytes == 0):
            try:
                self.tamano_bytes = self.fichero.size
                super().save(update_fields=["tamano_bytes"])
            except Exception:
                pass

    @property
    def tamano_kb(self):
        return self.tamano_bytes / 1024.0

    @property
    def tamano_mb(self):
        return self.tamano_bytes / (1024.0 * 1024.0)
    
    @property
    def storage_label(self):
        """
        Etiqueta pública definida por el proveedor documental.

        El código técnico del provider no tiene que coincidir con
        el nombre mostrado al usuario.
        """
        try:
            from .storage_providers import get_storage_provider

            provider = get_storage_provider(
                self.storage_provider
            )

            return (
                getattr(provider, "public_label", "")
                or self.storage_provider.upper()
            )
        except Exception:
            return (
                self.storage_provider
                or "local"
            ).upper()

    @property
    def online_edit_supported(self):
        """
        Capacidad ofrecida por el StorageProvider activo.
        """
        try:
            from .storage_providers import get_storage_provider

            provider = get_storage_provider(
                self.storage_provider
            )

            return bool(
                provider.supports_online_edit(self)
            )
        except Exception:
            return False

    @property
    def mimetype(self):
        """
        MIME neutral respecto al proveedor documental.

        Prioriza el tipo persistido por el provider y, como
        alternativa, lo deduce del nombre lógico del documento.
        """
        if self.mime_type:
            return self.mime_type

        candidate = (
            self.nombre_original
            or self.nombre_logico
            or (
                self.fichero.name
                if self.fichero
                else ""
            )
        )

        tipo, _ = mimetypes.guess_type(candidate)
        return tipo or ""

    @property
    def es_imagen(self):
        return self.mimetype.startswith("image/")

    @property
    def es_pdf(self):
        return self.mimetype == "application/pdf"


class ArchivoLog(models.Model):
    """Registro de acciones realizadas sobre un archivo.

    Permite auditar quién ha subido, renombrado, movido, eliminado o descargado
    un fichero y cuándo lo hizo.
    """

    ACCION_CHOICES = [
        ("SUBIR", "Subida"),
        ("RENOMBRAR", "Renombrar"),
        ("MOVER", "Mover"),
        ("ELIMINAR", "Eliminar"),
        ("DESCARGAR", "Descargar"),
    ]

    archivo = models.ForeignKey(
        Archivo,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    usuario = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archivo_logs",
    )
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "log de archivo"
        verbose_name_plural = "logs de archivo"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.archivo.nombre_original} — {self.accion} — {self.fecha:%Y-%m-%d %H:%M}"

# ARCHIVOS_RBAC_P1A_FOUNDATION_V1
class ReglaAccesoRaizCloud(models.Model):
    """
    Define qué grupos funcionales pueden acceder
    a una raíz documental de INTASA Cloud.

    Las subcarpetas heredan la autorización de
    la raíz. La capacidad de lectura o gestión
    se resuelve de forma independiente mediante
    permisos Django.
    """

    nombre_raiz = models.CharField(
        "Raíz documental",
        max_length=255,
        unique=True,
        help_text=(
            "Nombre exacto de la carpeta raíz "
            "visible mediante INTASA Cloud."
        ),
    )

    grupos = models.ManyToManyField(
        "auth.Group",
        verbose_name="Grupos autorizados",
        related_name=(
            "reglas_acceso_raiz_cloud"
        ),
        blank=True,
    )

    visible_para_todos = models.BooleanField(
        "Visible para todos los usuarios con acceso",
        default=False,
        help_text=(
            "Permite esta raíz a cualquier usuario "
            "que tenga la capacidad documental "
            "requerida."
        ),
    )

    activa = models.BooleanField(
        "Activa",
        default=True,
    )

    descripcion = models.CharField(
        "Descripción",
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "nombre_raiz",
        )

        verbose_name = (
            "Regla de acceso a raíz Cloud"
        )

        verbose_name_plural = (
            "Reglas de acceso a raíces Cloud"
        )

    def __str__(self):
        return self.nombre_raiz

    def save(self, *args, **kwargs):
        self.nombre_raiz = str(
            self.nombre_raiz
            or ""
        ).strip().strip("/")

        if not self.nombre_raiz:
            raise ValueError(
                "La raíz documental no puede "
                "estar vacía."
            )

        return super().save(
            *args,
            **kwargs,
        )
