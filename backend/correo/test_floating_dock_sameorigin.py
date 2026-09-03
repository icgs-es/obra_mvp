from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Permission,
)
from django.template.loader import (
    render_to_string,
)
from django.test import (
    RequestFactory,
    TestCase,
)
from django.urls import reverse

from .models import CuentaCorreo


User = get_user_model()


class FloatingDockSameOriginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dock-sameorigin-user",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        self.user.user_permissions.add(
            permission
        )

        CuentaCorreo.objects.create(
            usuario=self.user,
            direccion="dock@example.com",
            nombre_remitente="Dock User",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            credencial_cifrada="encrypted-test",
            activa=True,
            verificada=True,
        )

        self.client.force_login(
            self.user
        )

    @patch(
        "correo.views.listar_bandeja"
    )
    def test_dock_allows_same_origin_iframe(
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

        self.assertEqual(
            response.headers.get(
                "X-Frame-Options"
            ),
            "SAMEORIGIN",
        )

    def test_work_menu_contains_mail_link(
        self,
    ):
        request = RequestFactory().get(
            "/app/"
        )

        request.user = self.user

        html = render_to_string(
            "base.html",
            request=request,
        )

        self.assertIn(
            "Correo y comunicaciones",
            html,
        )

        self.assertIn(
            reverse(
                "correo:inicio"
            ),
            html,
        )
