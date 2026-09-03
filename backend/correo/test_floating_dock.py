from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Permission,
)
from django.test import (
    RequestFactory,
    TestCase,
)
from django.template.loader import (
    render_to_string,
)
from django.urls import reverse

from .models import CuentaCorreo


User = get_user_model()


class FloatingDockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="floating-mail-user",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        self.user.user_permissions.add(
            permission
        )

        self.account = CuentaCorreo.objects.create(
            usuario=self.user,
            direccion="floating@example.com",
            nombre_remitente="Floating User",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            credencial_cifrada="encrypted-test",
            activa=True,
            verificada=True,
        )

        self.factory = RequestFactory()

    @patch(
        "correo.services.obtener_contadores_bandeja"
    )
    def test_counter_endpoint_returns_json(
        self,
        mocked_counters,
    ):
        mocked_counters.return_value = {
            "no_leidos": 7,
            "total_mensajes": 120,
        }

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "correo:contador_flotante"
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertEqual(
            payload["no_leidos"],
            7,
        )

        self.assertEqual(
            payload["total_mensajes"],
            120,
        )

    def test_base_shows_dock_for_configured_user(
        self,
    ):
        request = self.factory.get(
            "/app/"
        )

        request.user = self.user

        html = render_to_string(
            "base.html",
            request=request,
        )

        self.assertIn(
            "intasa-correo-dock-launcher",
            html,
        )

        self.assertIn(
            "floating@example.com",
            html,
        )

    def test_base_hides_dock_without_account(
        self,
    ):
        user = User.objects.create_user(
            username="without-mail-account",
        )

        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        user.user_permissions.add(
            permission
        )

        request = self.factory.get(
            "/app/"
        )

        request.user = user

        html = render_to_string(
            "base.html",
            request=request,
        )

        self.assertNotIn(
            "intasa-correo-dock-launcher",
            html,
        )

    @patch(
        "correo.views.listar_bandeja"
    )
    def test_dock_mode_has_no_nested_launcher(
        self,
        mocked_inbox,
    ):
        mocked_inbox.return_value = (
            SimpleNamespace(
                mensajes=(),
                no_leidos=0,
                total_mensajes=0,
            )
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "correo:inicio"
            )
            + "?dock=1",
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        content = response.content.decode(
            "utf-8"
        )

        self.assertIn(
            "correo-page-dock",
            content,
        )

        self.assertNotIn(
            "intasa-correo-dock-launcher",
            content,
        )
