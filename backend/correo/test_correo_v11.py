from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CuentaCorreo
from .services import (
    ResultadoBandeja,
    _bodystructure_has_attachment,
    _imap_search_date,
    listar_bandeja,
)
from .views import (
    _puede_gestionar_archivos_cloud,
)


User = get_user_model()


class FakeInboxImap:
    def __init__(self):
        self.calls = []
        self.logged_out = False

    def select(self, mailbox, readonly=False):
        self.calls.append(
            (
                "select",
                mailbox,
                readonly,
            )
        )
        return "OK", [b"100"]

    def uid(self, *args):
        self.calls.append(args)

        if args == (
            "search",
            None,
            "UNSEEN",
        ):
            return "OK", [b""]

        if (
            len(args) == 4
            and args[0] == "search"
            and args[1] is None
            and args[2] == "SINCE"
        ):
            return "OK", [b""]

        raise AssertionError(
            f"Comando IMAP inesperado: {args!r}"
        )

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]


class CorreoInboxServiceV11Tests(
    SimpleTestCase
):
    @patch(
        "correo.services._open_imap"
    )
    def test_30_days_uses_imap_since(
        self,
        open_imap,
    ):
        fake = FakeInboxImap()

        open_imap.return_value = (
            fake,
            "secret",
        )

        cuenta = SimpleNamespace(
            activa=True,
            verificada=True,
        )

        result = listar_bandeja(
            cuenta,
            days=30,
            page=1,
            page_size=50,
        )

        expected_since = _imap_search_date(
            timezone.localdate()
            - timedelta(days=29)
        )

        self.assertIn(
            (
                "search",
                None,
                "SINCE",
                expected_since,
            ),
            fake.calls,
        )

        self.assertEqual(
            result.period_total,
            0,
        )

        self.assertTrue(
            fake.logged_out
        )


class CorreoInboxViewV11Tests(
    TestCase
):
    def setUp(self):
        self.user = User.objects.create_user(
            username="correo-v11",
            password="test-password",
        )

        permiso = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        self.user.user_permissions.add(
            permiso
        )

        self.account = CuentaCorreo.objects.create(
            usuario=self.user,
            direccion="correo-v11@example.com",
            activa=True,
            verificada=True,
        )

        self.client.force_login(
            self.user
        )

        self.url = reverse(
            "correo:inicio"
        )

    @patch(
        "correo.views.listar_bandeja"
    )
    def test_default_is_7_days(
        self,
        mocked_inbox,
    ):
        mocked_inbox.return_value = ResultadoBandeja(
            mensajes=(),
            no_leidos=0,
            total_mensajes=100,
        )

        response = self.client.get(
            self.url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        mocked_inbox.assert_called_once_with(
            self.account,
            days=7,
            page=1,
            page_size=50,
        )

    @patch(
        "correo.views.listar_bandeja"
    )
    def test_filter_30_days_page_2(
        self,
        mocked_inbox,
    ):
        mocked_inbox.return_value = ResultadoBandeja(
            mensajes=(),
            no_leidos=0,
            total_mensajes=100,
            period_total=80,
            page=2,
            page_size=50,
            total_pages=2,
            has_previous=True,
            has_next=False,
        )

        response = self.client.get(
            self.url + "?dias=30&page=2",
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        mocked_inbox.assert_called_once_with(
            self.account,
            days=30,
            page=2,
            page_size=50,
        )


class CorreoAttachmentIndicatorV12Tests(
    SimpleTestCase
):
    def test_bodystructure_attachment_disposition(
        self,
    ):
        metadata = (
            b'1 (UID 123 BODYSTRUCTURE '
            b'("APPLICATION" "PDF" '
            b'("NAME" "factura.pdf") NIL NIL '
            b'"BASE64" 1000 NIL '
            b'("ATTACHMENT" '
            b'("FILENAME" "factura.pdf")) NIL NIL))'
        )

        self.assertTrue(
            _bodystructure_has_attachment(
                metadata
            )
        )

    def test_bodystructure_filename_is_attachment(
        self,
    ):
        metadata = (
            b'1 (UID 124 BODYSTRUCTURE '
            b'("APPLICATION" "OCTET-STREAM" '
            b'("NAME" "documento.xlsx") '
            b'NIL NIL "BASE64" 400 NIL NIL NIL NIL))'
        )

        self.assertTrue(
            _bodystructure_has_attachment(
                metadata
            )
        )

    def test_bodystructure_without_attachment(
        self,
    ):
        metadata = (
            b'1 (UID 125 BODYSTRUCTURE '
            b'("TEXT" "PLAIN" '
            b'("CHARSET" "UTF-8") '
            b'NIL NIL "7BIT" 120 5 NIL NIL NIL NIL))'
        )

        self.assertFalse(
            _bodystructure_has_attachment(
                metadata
            )
        )


class CorreoAttachmentPermissionV11Tests(
    TestCase
):
    def test_staff_alone_does_not_grant_save(
        self,
    ):
        staff_only = User.objects.create_user(
            username="correo-staff-only",
            password="x",
            is_staff=True,
        )

        self.assertFalse(
            _puede_gestionar_archivos_cloud(
                staff_only
            )
        )

        functional_user = User.objects.create_user(
            username="correo-functional-files",
            password="x",
            is_staff=False,
        )

        permiso = Permission.objects.get(
            content_type__app_label="archivos",
            codename="add_archivo",
        )

        functional_user.user_permissions.add(
            permiso
        )

        self.assertTrue(
            _puede_gestionar_archivos_cloud(
                functional_user
            )
        )
