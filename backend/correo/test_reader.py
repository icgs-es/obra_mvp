from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import (
    SimpleTestCase,
    TestCase,
)
from django.urls import reverse
from django.utils import timezone

from .models import CuentaCorreo
from .reader import (
    AdjuntoResumen,
    MensajeDetalle,
    ResultadoEstadoLectura,
    html_to_safe_text,
)


User = get_user_model()


class SafeHtmlTextTests(SimpleTestCase):
    def test_html_is_converted_to_safe_text(self):
        value = """
        <html>
          <head>
            <style>.hidden {display:none}</style>
            <script>alert("x")</script>
          </head>
          <body>
            <h1>Factura recibida</h1>
            <p>Importe: 125 euros</p>
            <img src="https://tracker.example/pixel">
          </body>
        </html>
        """

        result = html_to_safe_text(
            value
        )

        self.assertIn(
            "Factura recibida",
            result,
        )

        self.assertIn(
            "Importe: 125 euros",
            result,
        )

        self.assertNotIn(
            "alert",
            result,
        )

        self.assertNotIn(
            "tracker.example",
            result,
        )


class ReaderViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reader-user",
            email="reader@example.com",
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
            direccion="reader@example.com",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        self.detail_url = reverse(
            "correo:detalle_mensaje",
            args=(123,),
        )

        self.state_url = reverse(
            "correo:estado_mensaje",
            args=(123,),
        )

        self.client.force_login(
            self.user
        )

    @patch(
        "correo.views.obtener_mensaje"
    )
    def test_owner_can_load_message_json(
        self,
        mocked_reader,
    ):
        mocked_reader.return_value = MensajeDetalle(
            uid="123",
            asunto="Mensaje seguro",
            remitente_nombre="Proveedor",
            remitente_email="proveedor@example.com",
            destinatarios="reader@example.com",
            copia="",
            fecha=timezone.now(),
            fecha_original="",
            cuerpo_texto="Contenido de prueba",
            leido=False,
            tamano_bytes=2048,
            contenido_recortado=False,
            adjuntos=(
                AdjuntoResumen(
                    nombre="factura.pdf",
                    tipo_contenido="application/pdf",
                    tamano_bytes=4096,
                ),
            ),
        )

        response = self.client.get(
            self.detail_url,
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
            payload["mensaje"]["asunto"],
            "Mensaje seguro",
        )

        self.assertEqual(
            payload["mensaje"]["cuerpo_texto"],
            "Contenido de prueba",
        )

        self.assertEqual(
            len(
                payload["mensaje"]["adjuntos"]
            ),
            1,
        )

        self.assertIn(
            "no-store",
            response["Cache-Control"],
        )

    @patch(
        "correo.views.cambiar_estado_lectura"
    )
    def test_owner_can_mark_message_read(
        self,
        mocked_state,
    ):
        mocked_state.return_value = (
            ResultadoEstadoLectura(
                uid="123",
                leido=True,
                no_leidos=4,
            )
        )

        response = self.client.post(
            self.state_url,
            {
                "leido": "1",
            },
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

        self.assertTrue(
            payload["leido"]
        )

        self.assertEqual(
            payload["no_leidos"],
            4,
        )

    def test_invalid_state_is_rejected(self):
        response = self.client.post(
            self.state_url,
            {
                "leido": "incorrecto",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_other_user_cannot_read_owner_mail(self):
        other = User.objects.create_user(
            username="other-reader",
            email="other@example.com",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="correo",
            codename="use_correo",
        )

        other.user_permissions.add(
            permission
        )

        self.client.force_login(
            other
        )

        response = self.client.get(
            self.detail_url,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            404,
        )


# INTASA_CORREO_V1C1_STATE_TEST
class _FakeStateImap:
    def __init__(self):
        self.calls = []
        self.logged_out = False

    def select(
        self,
        mailbox,
        readonly=False,
    ):
        self.calls.append(
            (
                "select",
                mailbox,
                readonly,
            )
        )

        return (
            "OK",
            [b"10"],
        )

    def uid(
        self,
        command,
        *args,
    ):
        self.calls.append(
            (
                "uid",
                command,
                args,
            )
        )

        normalized = command.lower()

        if normalized == "store":
            # IONOS puede aceptar UID STORE y devolver
            # una respuesta vacía o no estructurada.
            return (
                "OK",
                [None],
            )

        if normalized == "search":
            return (
                "OK",
                [b"20 21 22"],
            )

        raise AssertionError(
            f"Comando IMAP inesperado: {command}"
        )

    def logout(self):
        self.logged_out = True


class ReaderStateServiceTests(SimpleTestCase):
    @patch(
        "correo.reader._open_imap"
    )
    def test_mark_read_uses_uid_store_without_fetch_precheck(
        self,
        mocked_open,
    ):
        from .reader import cambiar_estado_lectura

        fake_imap = _FakeStateImap()

        mocked_open.return_value = (
            fake_imap,
            "secret",
        )

        account = CuentaCorreo(
            direccion="reader@example.com",
            imap_host="imap.ionos.es",
            imap_port=993,
            activa=True,
            verificada=True,
        )

        result = cambiar_estado_lectura(
            account,
            123,
            True,
        )

        self.assertTrue(
            result.leido
        )

        self.assertEqual(
            result.no_leidos,
            3,
        )

        uid_commands = [
            call[1].lower()
            for call in fake_imap.calls
            if call[0] == "uid"
        ]

        self.assertIn(
            "store",
            uid_commands,
        )

        self.assertNotIn(
            "fetch",
            uid_commands,
        )

        self.assertTrue(
            fake_imap.logged_out
        )
