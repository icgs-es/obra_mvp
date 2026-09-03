from django.conf import settings
from django.db import models

from .crypto import decrypt_password, encrypt_password


class CuentaCorreo(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cuenta_correo",
        verbose_name="Usuario de INTASA",
    )

    direccion = models.EmailField(
        unique=True,
        verbose_name="Dirección de correo",
    )

    nombre_remitente = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Nombre del remitente",
    )

    imap_host = models.CharField(
        max_length=255,
        default="imap.ionos.es",
        verbose_name="Servidor IMAP",
    )

    imap_port = models.PositiveIntegerField(
        default=993,
        verbose_name="Puerto IMAP",
    )

    smtp_host = models.CharField(
        max_length=255,
        default="smtp.ionos.es",
        verbose_name="Servidor SMTP",
    )

    smtp_port = models.PositiveIntegerField(
        default=465,
        verbose_name="Puerto SMTP",
    )

    credencial_cifrada = models.TextField(
        blank=True,
        editable=False,
        verbose_name="Credencial cifrada",
    )

    activa = models.BooleanField(
        default=True,
        verbose_name="Cuenta activa",
    )

    verificada = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="Conexión verificada",
    )

    ultima_prueba = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Última prueba",
    )

    ultimo_error = models.TextField(
        blank=True,
        editable=False,
        verbose_name="Último error",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "cuenta de correo"
        verbose_name_plural = "cuentas de correo"
        ordering = ("usuario__username",)
        permissions = (
            (
                "use_correo",
                "Puede utilizar el correo corporativo",
            ),
        )

    def __str__(self) -> str:
        return (
            f"{self.usuario.get_username()} · "
            f"{self.direccion}"
        )

    @property
    def tiene_contrasena(self) -> bool:
        return bool(self.credencial_cifrada)

    def set_password(self, raw_password: str) -> None:
        self.credencial_cifrada = encrypt_password(
            raw_password
        )
        self.verificada = False
        self.ultimo_error = ""

    def get_password(self) -> str:
        return decrypt_password(
            self.credencial_cifrada
        )
