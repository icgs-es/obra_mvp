from django import forms
from django.contrib import admin, messages
from django.utils import timezone

from .models import CuentaCorreo
from .services import probar_conexion


class CuentaCorreoAdminForm(forms.ModelForm):
    nueva_contrasena = forms.CharField(
        required=False,
        label="Contraseña del buzón",
        help_text=(
            "Se cifra antes de guardarse. "
            "Déjala vacía para conservar la actual."
        ),
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "new-password",
            },
        ),
    )

    confirmar_contrasena = forms.CharField(
        required=False,
        label="Confirmar contraseña",
        help_text=(
            "Repite la contraseña solamente "
            "cuando quieras crearla o cambiarla."
        ),
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "new-password",
            },
        ),
    )

    class Meta:
        model = CuentaCorreo
        fields = (
            "usuario",
            "direccion",
            "nombre_remitente",
            "imap_host",
            "imap_port",
            "smtp_host",
            "smtp_port",
            "activa",
        )

    def clean(self):
        cleaned = super().clean()

        password = cleaned.get(
            "nueva_contrasena"
        )

        confirmation = cleaned.get(
            "confirmar_contrasena"
        )

        if not self.instance.pk and not password:
            self.add_error(
                "nueva_contrasena",
                (
                    "Debes indicar la contraseña "
                    "al crear la cuenta."
                ),
            )

        if password or confirmation:
            if not password:
                self.add_error(
                    "nueva_contrasena",
                    "Debes indicar la contraseña.",
                )

            if not confirmation:
                self.add_error(
                    "confirmar_contrasena",
                    (
                        "Debes repetir "
                        "la contraseña."
                    ),
                )

            if (
                password
                and confirmation
                and password != confirmation
            ):
                self.add_error(
                    "confirmar_contrasena",
                    (
                        "Las contraseñas "
                        "no coinciden."
                    ),
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False
        )

        password = self.cleaned_data.get(
            "nueva_contrasena"
        )

        if password:
            instance.set_password(
                password
            )

        if commit:
            instance.save()

        return instance


@admin.register(CuentaCorreo)
class CuentaCorreoAdmin(admin.ModelAdmin):
    form = CuentaCorreoAdminForm

    list_display = (
        "usuario",
        "direccion",
        "activa",
        "verificada",
        "estado_contrasena",
        "ultima_prueba",
    )

    list_filter = (
        "activa",
        "verificada",
    )

    search_fields = (
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "direccion",
    )

    readonly_fields = (
        "estado_contrasena",
        "verificada",
        "ultima_prueba",
        "ultimo_error",
        "creado_en",
        "actualizado_en",
    )

    fieldsets = (
        (
            "Asignación",
            {
                "fields": (
                    "usuario",
                    "direccion",
                    "nombre_remitente",
                    "activa",
                )
            },
        ),
        (
            "Servidor IONOS",
            {
                "fields": (
                    "imap_host",
                    "imap_port",
                    "smtp_host",
                    "smtp_port",
                    "nueva_contrasena",
                    "confirmar_contrasena",
                    "estado_contrasena",
                )
            },
        ),
        (
            "Verificación",
            {
                "fields": (
                    "verificada",
                    "ultima_prueba",
                    "ultimo_error",
                )
            },
        ),
        (
            "Auditoría",
            {
                "classes": ("collapse",),
                "fields": (
                    "creado_en",
                    "actualizado_en",
                ),
            },
        ),
    )

    actions = (
        "probar_conexiones_seleccionadas",
    )

    @admin.display(
        boolean=True,
        description="Contraseña configurada",
    )
    def estado_contrasena(
        self,
        obj,
    ):
        return obj.tiene_contrasena

    @admin.action(
        description=(
            "Probar conexión IMAP y SMTP "
            "de las cuentas seleccionadas"
        )
    )
    def probar_conexiones_seleccionadas(
        self,
        request,
        queryset,
    ):
        for cuenta in queryset:
            resultado = probar_conexion(
                cuenta
            )

            cuenta.verificada = (
                resultado.correcta
            )

            cuenta.ultima_prueba = (
                timezone.now()
            )

            cuenta.ultimo_error = (
                ""
                if resultado.correcta
                else resultado.detalle
            )

            cuenta.save(
                update_fields=(
                    "verificada",
                    "ultima_prueba",
                    "ultimo_error",
                    "actualizado_en",
                )
            )

            if resultado.correcta:
                self.message_user(
                    request,
                    (
                        f"{cuenta.direccion}: "
                        "conexión IMAP y SMTP correcta."
                    ),
                    level=messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    (
                        f"{cuenta.direccion}: "
                        f"{resultado.detalle}"
                    ),
                    level=messages.ERROR,
                )

    def has_module_permission(
        self,
        request,
    ):
        return request.user.is_superuser

    def has_view_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser

    def has_add_permission(
        self,
        request,
    ):
        return request.user.is_superuser

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser
