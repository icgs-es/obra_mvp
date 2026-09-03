from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .admin import CuentaCorreoAdminForm
from .models import CuentaCorreo
from .services import (
    MensajeResumen,
    ResultadoBandeja,
)


User = get_user_model()


class CuentaCorreoCryptoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="correo-test",
            email="correo-test@example.com",
            password="test-password",
        )

    def test_password_is_encrypted(self):
        cuenta = CuentaCorreo(
            usuario=self.user,
            direccion="correo-test@example.com",
        )

        cuenta.set_password(
            "clave-super-secreta"
        )

        self.assertNotIn(
            "clave-super-secreta",
            cuenta.credencial_cifrada,
        )

        self.assertEqual(
            cuenta.get_password(),
            "clave-super-secreta",
        )

    def test_password_is_required_on_create(self):
        form = CuentaCorreoAdminForm(
            data={
                "usuario": self.user.pk,
                "direccion": (
                    "correo-test@example.com"
                ),
                "nombre_remitente": "Prueba",
                "imap_host": "imap.ionos.es",
                "imap_port": 993,
                "smtp_host": "smtp.ionos.es",
                "smtp_port": 465,
                "activa": True,
            }
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "nueva_contrasena",
            form.errors,
        )

    def test_password_confirmation_must_match(self):
        form = CuentaCorreoAdminForm(
            data={
                "usuario": self.user.pk,
                "direccion": (
                    "correo-test@example.com"
                ),
                "nombre_remitente": "Prueba",
                "imap_host": "imap.ionos.es",
                "imap_port": 993,
                "smtp_host": "smtp.ionos.es",
                "smtp_port": 465,
                "activa": True,
                "nueva_contrasena": "uno",
                "confirmar_contrasena": "dos",
            }
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "confirmar_contrasena",
            form.errors,
        )


class CuentaCorreoAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="usuario-correo",
            email="usuario@example.com",
            password="test-password",
        )

        self.url = reverse(
            "correo:inicio"
        )

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_user_without_permission_gets_403(self):
        self.client.force_login(
            self.user
        )

        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_user_with_permission_can_open_without_account(self):
        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        self.user.user_permissions.add(
            permission
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "todavía no está configurada",
        )

    @patch(
        "correo.views.listar_bandeja"
    )
    def test_owner_sees_mocked_inbox(
        self,
        mocked_inbox,
    ):
        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        self.user.user_permissions.add(
            permission
        )

        account = CuentaCorreo.objects.create(
            usuario=self.user,
            direccion="usuario@example.com",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        account.set_password(
            "test-password"
        )

        account.save(
            update_fields=(
                "credencial_cifrada",
            )
        )

        mocked_inbox.return_value = ResultadoBandeja(
            mensajes=(
                MensajeResumen(
                    uid="123",
                    asunto="Correo de prueba",
                    remitente_nombre="Proveedor",
                    remitente_email=(
                        "proveedor@example.com"
                    ),
                    fecha=None,
                    fecha_original="",
                    leido=False,
                    tamano_bytes=2048,
                ),
            ),
            no_leidos=1,
            total_mensajes=8,
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Correo de prueba",
        )

        self.assertContains(
            response,
            "1 sin leer",
        )

        mocked_inbox.assert_called_once()

    def test_superuser_can_open(self):
        superuser = User.objects.create_superuser(
            username="super-correo",
            email="super@example.com",
            password="test-password",
        )

        self.client.force_login(
            superuser
        )

        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
