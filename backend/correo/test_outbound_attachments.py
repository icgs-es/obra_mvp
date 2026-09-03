from email.message import EmailMessage

from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import SimpleTestCase

from .sender import (
    MAX_OUTBOUND_ATTACHMENTS_BYTES,
    CorreoValidationError,
    agregar_adjuntos_mensaje,
    preparar_adjuntos_salida,
)


class OutboundAttachmentTests(
    SimpleTestCase
):
    def test_prepare_pdf_attachment(self):
        uploaded = SimpleUploadedFile(
            name="factura.pdf",
            content=b"PDF-DATA",
            content_type="application/pdf",
        )

        prepared = (
            preparar_adjuntos_salida(
                [uploaded]
            )
        )

        self.assertEqual(
            len(prepared),
            1,
        )

        self.assertEqual(
            prepared[0]["nombre"],
            "factura.pdf",
        )

        self.assertEqual(
            prepared[0]["maintype"],
            "application",
        )

        self.assertEqual(
            prepared[0]["subtype"],
            "pdf",
        )

        self.assertEqual(
            prepared[0]["contenido"],
            b"PDF-DATA",
        )

    def test_unknown_type_uses_safe_mime(self):
        uploaded = SimpleUploadedFile(
            name="datos.unknownextension",
            content=b"DATA",
            content_type="invalid content type",
        )

        prepared = (
            preparar_adjuntos_salida(
                [uploaded]
            )
        )

        self.assertEqual(
            prepared[0]["tipo_contenido"],
            "application/octet-stream",
        )

    def test_oversized_attachment_is_rejected(
        self,
    ):
        class OversizedFile:
            name = "grande.bin"
            content_type = (
                "application/octet-stream"
            )
            size = (
                MAX_OUTBOUND_ATTACHMENTS_BYTES
                + 1
            )

            def read(self):
                raise AssertionError(
                    "No debe leer un archivo rechazado."
                )

        with self.assertRaises(
            CorreoValidationError
        ):
            preparar_adjuntos_salida(
                [
                    OversizedFile(),
                ]
            )

    def test_attachment_is_added_to_mime_message(
        self,
    ):
        uploaded = SimpleUploadedFile(
            name="imagen.png",
            content=b"PNG-DATA",
            content_type="image/png",
        )

        prepared = (
            preparar_adjuntos_salida(
                [uploaded]
            )
        )

        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "target@example.com"
        message["Subject"] = "Prueba"
        message.set_content("Mensaje")

        agregar_adjuntos_mensaje(
            message,
            prepared,
        )

        attachments = list(
            message.iter_attachments()
        )

        self.assertEqual(
            len(attachments),
            1,
        )

        self.assertEqual(
            attachments[0].get_filename(),
            "imagen.png",
        )

        self.assertEqual(
            attachments[0].get_content_type(),
            "image/png",
        )

        self.assertEqual(
            attachments[0].get_payload(
                decode=True
            ),
            b"PNG-DATA",
        )
