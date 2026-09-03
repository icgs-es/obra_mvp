from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from archivos.models import (
    Archivo,
    Carpeta,
)

from .attachments import (
    AdjuntoContenido,
    obtener_adjunto,
)
from .models import CuentaCorreo
from .reader import (
    AdjuntoResumen,
    MensajeDetalle,
)


User = get_user_model()


class FakeAttachmentImap:
    def __init__(
        self,
        raw_message,
    ):
        self.raw_message = raw_message
        self.logged_out = False

    def select(
        self,
        mailbox,
        readonly=False,
    ):
        return (
            "OK",
            [b"1"],
        )

    def uid(
        self,
        command,
        *args,
    ):
        if command.lower() != "fetch":
            raise AssertionError(
                f"Comando inesperado: {command}"
            )

        return (
            "OK",
            [
                (
                    b"1 (BODY[] {100})",
                    self.raw_message,
                ),
            ],
        )

    def logout(self):
        self.logged_out = True


class AttachmentReaderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="attachment-reader",
        )

        self.account = CuentaCorreo(
            usuario=self.user,
            direccion="reader@example.com",
            imap_host="imap.ionos.es",
            activa=True,
            verificada=True,
        )

    @patch(
        "correo.attachments._open_imap"
    )
    @patch(
        "correo.attachments.obtener_mensaje"
    )
    def test_obtiene_adjunto_por_indice(
        self,
        mocked_detail,
        mocked_open,
    ):
        message = EmailMessage()

        message["From"] = (
            "proveedor@example.com"
        )

        message["To"] = (
            "reader@example.com"
        )

        message["Subject"] = "Factura"

        message.set_content(
            "Adjunto factura."
        )

        message.add_attachment(
            b"PDF-CONTENT",
            maintype="application",
            subtype="pdf",
            filename="factura.pdf",
        )

        raw_message = message.as_bytes()

        fake_imap = FakeAttachmentImap(
            raw_message
        )

        mocked_open.return_value = (
            fake_imap,
            "secret",
        )

        mocked_detail.return_value = (
            MensajeDetalle(
                uid="123",
                asunto="Factura",
                remitente_nombre="Proveedor",
                remitente_email=(
                    "proveedor@example.com"
                ),
                destinatarios=(
                    "reader@example.com"
                ),
                copia="",
                fecha=timezone.now(),
                fecha_original="",
                cuerpo_texto="Adjunto factura.",
                leido=True,
                tamano_bytes=len(
                    raw_message
                ),
                contenido_recortado=False,
                adjuntos=(
                    AdjuntoResumen(
                        nombre="factura.pdf",
                        tipo_contenido=(
                            "application/pdf"
                        ),
                        tamano_bytes=11,
                    ),
                ),
            )
        )

        result = obtener_adjunto(
            self.account,
            123,
            0,
        )

        self.assertEqual(
            result.nombre,
            "factura.pdf",
        )

        self.assertEqual(
            result.tipo_contenido,
            "application/pdf",
        )

        self.assertEqual(
            result.contenido,
            b"PDF-CONTENT",
        )

        self.assertTrue(
            fake_imap.logged_out
        )


class AttachmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="attachment-user",
            email="attachment@example.com",
            password="test-password",
            is_staff=True,
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
            direccion="attachment@example.com",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        self.client.force_login(
            self.user
        )

        self.attachment = AdjuntoContenido(
            indice=0,
            nombre="documento.pdf",
            tipo_contenido="application/pdf",
            tamano_bytes=7,
            contenido=b"PDFDATA",
        )

    @patch(
        "correo.views.obtener_adjunto"
    )
    def test_download_is_private_and_safe(
        self,
        mocked_attachment,
    ):
        mocked_attachment.return_value = (
            self.attachment
        )

        response = self.client.get(
            reverse(
                "correo:descargar_adjunto",
                args=(
                    123,
                    0,
                ),
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.content,
            b"PDFDATA",
        )

        self.assertIn(
            "attachment",
            response[
                "Content-Disposition"
            ],
        )

        self.assertEqual(
            response[
                "Cache-Control"
            ],
            (
                "private, no-store, no-cache, "
                "must-revalidate, max-age=0"
            ),
        )

    @patch(
        "archivos.activity.registrar_subida_documental"
    )
    @patch(
        "archivos.cloud_references.upsert_cloud_uploaded_reference"
    )
    @patch(
        "archivos.cloud_views._cloud_index_folder"
    )
    @patch(
        "archivos.team_scope.resolve_document_team"
    )
    @patch(
        "archivos.cloud_gateway.NextcloudCloudGateway"
    )
    @patch(
        "correo.views.obtener_adjunto"
    )
    def test_save_attachment_uses_nextcloud_gateway(
        self,
        mocked_attachment,
        gateway_class,
        resolve_team,
        cloud_index_folder,
        upsert_reference,
        register_activity,
    ):
        team = Team.objects.create(
            name="Empresa adjuntos",
        )

        folder = Carpeta.objects.create(
            nombre="Índice cloud",
            slug="intasa-cloud-system-test",
            owner=self.user,
            visibilidad="GLOBAL",
        )

        archivo = Archivo.objects.create(
            carpeta=folder,
            team=team,
            fichero="",
            nombre_original="documento.pdf",
            nombre_logico="documento.pdf",
            subido_por=self.user,
            tamano_bytes=7,
            storage_provider="nextcloud",
            storage_key=(
                "Gestion/documento.pdf"
            ),
            storage_object_id="remote-777",
            mime_type="application/pdf",
        )

        mocked_attachment.return_value = (
            self.attachment
        )

        gateway = gateway_class.return_value

        gateway.normalize_path.return_value = (
            "Gestion"
        )

        gateway.upload_file.return_value = {
            "storage_key": (
                "Gestion/documento.pdf"
            ),
            "file_id": "remote-777",
            "size": 7,
            "etag": "etag-777",
            "content_type": (
                "application/pdf"
            ),
        }

        resolve_team.return_value = team

        cloud_index_folder.return_value = (
            folder
        )

        upsert_reference.return_value = (
            archivo,
            True,
        )

        response = self.client.post(
            reverse(
                (
                    "correo:"
                    "guardar_adjunto_archivos"
                ),
                args=(
                    123,
                    0,
                ),
            ),
            {
                "path": "Gestion",
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

        self.assertEqual(
            payload["archivo_id"],
            archivo.pk,
        )

        gateway.upload_file.assert_called_once()

        upsert_reference.assert_called_once()

        register_activity.assert_called_once()


class AttachmentAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="attachment-no-staff",
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
            direccion="normal@example.com",
            imap_host="imap.ionos.es",
            smtp_host="smtp.ionos.es",
            activa=True,
            verificada=True,
        )

        self.client.force_login(
            self.user
        )

    def test_non_staff_cannot_browse_cloud_folders(
        self,
    ):
        response = self.client.get(
            reverse(
                "correo:carpetas_archivos"
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            403,
        )
