from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import (
    SimpleTestCase,
    TestCase,
)
from django.urls import reverse

from .models import CuentaCorreo
from .sender import (
    ResultadoEnvio,
    enviar_correo,
    normalizar_destinatarios,
)


User = get_user_model()


class FakeSMTP:
    def __init__(self):
        self.sent_message = None
        self.from_addr = None
        self.to_addrs = None
        self.quit_called = False

    def login(
        self,
        username,
        password,
    ):
        self.username = username
        self.password = password

    def send_message(
        self,
        message,
        from_addr=None,
        to_addrs=None,
    ):
        self.sent_message = message
        self.from_addr = from_addr
        self.to_addrs = tuple(
            to_addrs or ()
        )

    def quit(self):
        self.quit_called = True


class FakeImap:
    def __init__(self):
        self.appended = None
        self.logged_out = False

    def login(
        self,
        username,
        password,
    ):
        self.username = username
        self.password = password

    def list(self):
        return (
            "OK",
            [
                (
                    b'(\\HasNoChildren \\Sent) '
                    b'"/" "Elementos enviados"'
                ),
            ],
        )

    def status(
        self,
        mailbox,
        query,
    ):
        return (
            "OK",
            [b"MESSAGES 10"],
        )

    def append(
        self,
        mailbox,
        flags,
        date_time,
        message,
    ):
        self.appended = {
            "mailbox": mailbox,
            "flags": flags,
            "message": message,
        }

        return (
            "OK",
            [b"APPENDUID 1 20"],
        )

    def logout(self):
        self.logged_out = True


class RecipientValidationTests(
    SimpleTestCase
):
    def test_semicolon_and_duplicates(
        self,
    ):
        result = normalizar_destinatarios(
            (
                "uno@example.com; "
                "DOS@example.com, "
                "uno@example.com"
            ),
            required=True,
        )

        self.assertEqual(
            result,
            (
                "uno@example.com",
                "DOS@example.com",
            ),
        )


class SenderServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sender-user",
            email="sender@example.com",
            password="test-password",
        )

        self.account = CuentaCorreo.objects.create(
            usuario=self.user,
            direccion="sender@example.com",
            nombre_remitente="Sender User",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        self.account.set_password(
            "secret-password"
        )

        # Cambiar la contraseña invalida correctamente
        # la verificación. El test simula después una
        # comprobación IMAP/SMTP satisfactoria.
        self.account.verificada = True

        self.account.save(
            update_fields=(
                "credencial_cifrada",
                "verificada",
            )
        )

    @patch(
        "correo.sender.imaplib.IMAP4_SSL"
    )
    @patch(
        "correo.sender.smtplib.SMTP_SSL"
    )
    def test_send_and_copy_to_sent(
        self,
        smtp_class,
        imap_class,
    ):
        smtp = FakeSMTP()
        imap = FakeImap()

        smtp_class.return_value = smtp
        imap_class.return_value = imap

        result = enviar_correo(
            self.account,
            para="destino@example.com",
            copia="copia@example.com",
            copia_oculta="oculto@example.com",
            asunto="Mensaje de prueba",
            cuerpo="Contenido seguro",
        )

        self.assertTrue(
            result.copia_enviados
        )

        self.assertEqual(
            result.carpeta_enviados,
            "Elementos enviados",
        )

        self.assertEqual(
            smtp.from_addr,
            "sender@example.com",
        )

        self.assertIn(
            "destino@example.com",
            smtp.to_addrs,
        )

        self.assertIn(
            "oculto@example.com",
            smtp.to_addrs,
        )

        self.assertNotIn(
            "Bcc",
            smtp.sent_message,
        )

        self.assertIsNotNone(
            imap.appended
        )

        self.assertEqual(
            imap.appended["mailbox"],
            b'"Elementos enviados"',
        )

        self.assertTrue(
            smtp.quit_called
        )

        self.assertTrue(
            imap.logged_out
        )


class SendViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="send-view-user",
            email="send-view@example.com",
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
            direccion="send-view@example.com",
            nombre_remitente="Send View",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        self.client.force_login(
            self.user
        )

        self.url = reverse(
            "correo:enviar_mensaje"
        )

    def set_nonce(
        self,
        value="nonce-test",
    ):
        session = self.client.session

        session[
            "correo_compose_nonces"
        ] = [value]

        session.save()

    @patch(
        "correo.views.enviar_correo"
    )
    def test_success_rotates_nonce(
        self,
        mocked_send,
    ):
        self.set_nonce()

        mocked_send.return_value = ResultadoEnvio(
            message_id="<test@example.com>",
            copia_enviados=True,
            carpeta_enviados="Sent",
            advertencia="",
        )

        response = self.client.post(
            self.url,
            {
                "nonce": "nonce-test",
                "modo": "nuevo",
                "source_uid": "",
                "para": "destino@example.com",
                "copia": "",
                "copia_oculta": "",
                "asunto": "Prueba",
                "cuerpo": "Contenido",
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
            payload["copia_enviados"]
        )

        self.assertTrue(
            payload["next_nonce"]
        )

        session_tokens = self.client.session[
            "correo_compose_nonces"
        ]

        self.assertNotIn(
            "nonce-test",
            session_tokens,
        )

    def test_invalid_nonce_is_rejected(
        self,
    ):
        self.set_nonce(
            "valid-token"
        )

        response = self.client.post(
            self.url,
            {
                "nonce": "invalid-token",
                "modo": "nuevo",
                "para": "destino@example.com",
                "asunto": "Prueba",
                "cuerpo": "Contenido",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            409,
        )
