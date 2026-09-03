import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from usuarios.models import Team

from .attachment_validation import (
    MAX_FILE_SIZE,
    validate_attachment,
    validate_attachment_batch,
)
from .forms import PreguntaIAForm
from .models import (
    AccesoConversacionIA,
    AdjuntoIA,
    ConversacionIA,
    MensajeIA,
    ProcesamientoMensajeIA,
    PurgaAdjuntoIAPendiente,
)
from .private_storage import private_ia_root, private_ia_storage


User = get_user_model()
RESULT = {
    "contenido": "Respuesta textual.",
    "proveedor": "openai",
    "modelo": "test-model",
    "request_id": "req-test",
    "tokens_entrada": 5,
    "tokens_salida": 3,
    "metadata": {"external_call": True, "store": False},
}


def upload(name, data, mime):
    return SimpleUploadedFile(name, data, content_type=mime)


def image_bytes(format_name):
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(stream, format=format_name)
    return stream.getvalue()


def ooxml_bytes(kind="docx", *, macro=False, ratio_bomb=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        content_type = (
            "application/vnd.ms-word.document.macroEnabled.main+xml"
            if macro
            else "application/xml"
        )
        archive.writestr("[Content_Types].xml", content_type)
        archive.writestr(
            "word/document.xml" if kind == "docx" else "xl/workbook.xml",
            "<root/>",
        )
        if macro:
            archive.writestr("word/vbaProject.bin", b"macro")
        if ratio_bomb:
            archive.writestr("word/large.xml", b"0" * 1024 * 1024)
    return stream.getvalue()


def valid_uploads():
    return (
        upload("document.pdf", b"%PDF-1.4\n%%EOF", "application/pdf"),
        upload("photo.jpg", image_bytes("JPEG"), "image/jpeg"),
        upload("photo.jpeg", image_bytes("JPEG"), "image/jpeg"),
        upload("image.png", image_bytes("PNG"), "image/png"),
        upload("image.webp", image_bytes("WEBP"), "image/webp"),
        upload(
            "document.docx",
            ooxml_bytes("docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        upload(
            "book.xlsx",
            ooxml_bytes("xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        upload("legacy.xls", bytes.fromhex("D0CF11E0A1B11AE1") + b"data", "application/vnd.ms-excel"),
        upload("table.csv", b"a,b\n1,2\n", "text/csv"),
        upload("notes.txt", b"safe text\n", "text/plain"),
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class AttachmentFoundationTests(TestCase):
    def setUp(self):
        self.private_tmp = tempfile.mkdtemp(prefix="ia_private_test_")
        private_ia_storage._location = self.private_tmp
        for cached in ("base_location", "location", "base_url"):
            private_ia_storage.__dict__.pop(cached, None)
        self.team = Team.objects.create(name="ATTACHMENTS TEST")
        self.owner = User.objects.create_user(username="att-owner")
        self.shared = User.objects.create_user(username="att-shared")
        self.outsider = User.objects.create_user(username="att-outsider")
        self.staff = User.objects.create_user(username="att-staff", is_staff=True)
        self.superuser = User.objects.create_superuser(username="att-root", email="root@example.test")
        permission = Permission.objects.get(
            content_type__app_label="intasa_ia", codename="use_intasa_ia"
        )
        for user in (self.owner, self.shared, self.outsider, self.staff):
            user.user_permissions.add(permission)
        self.team.members.add(self.owner, self.shared, self.outsider, self.staff)

    def tearDown(self):
        shutil.rmtree(self.private_tmp, ignore_errors=True)

    def conversation(self):
        conversation = ConversacionIA.objects.create(user=self.owner, team=None, titulo="Private")
        message = MensajeIA.objects.create(
            conversacion=conversation, rol=MensajeIA.Rol.USUARIO, contenido=""
        )
        return conversation, message

    def create_attachment(self, conversation, message, name="document.pdf"):
        return AdjuntoIA.objects.create(
            conversation=conversation,
            message=message,
            owner=self.owner,
            file=upload(name, b"%PDF-1.4\n%%EOF", "application/pdf"),
            original_name=name,
            safe_display_name=name,
            declared_mime="application/pdf",
            detected_mime="application/pdf",
            extension=".pdf",
            size_bytes=14,
            sha256="a" * 64,
            status=AdjuntoIA.Estado.READY,
        )

    def test_every_allowed_format_has_minimum_valid_sample(self):
        for candidate in valid_uploads():
            with self.subTest(candidate.name):
                self.assertEqual(validate_attachment(candidate)["size_bytes"], candidate.size)

    def test_one_and_five_files_are_accepted_and_sixth_is_rejected(self):
        self.assertEqual(len(validate_attachment_batch([valid_uploads()[0]])), 1)
        self.assertEqual(len(validate_attachment_batch(list(valid_uploads()[:5]))), 5)
        with self.assertRaises(ValidationError):
            validate_attachment_batch(list(valid_uploads()[:6]))

    def test_size_limits_allow_10mb_and_reject_individual_and_total_excess(self):
        exact = upload("exact.txt", b"x" * MAX_FILE_SIZE, "text/plain")
        self.assertEqual(validate_attachment(exact)["size_bytes"], MAX_FILE_SIZE)
        with self.assertRaises(ValidationError):
            validate_attachment(upload("large.txt", b"x" * (MAX_FILE_SIZE + 1), "text/plain"))
        files = [upload(f"part-{i}.txt", b"x" * (6 * 1024 * 1024), "text/plain") for i in range(5)]
        with self.assertRaises(ValidationError):
            validate_attachment_batch(files)

    def test_empty_false_mime_double_extension_corrupt_and_binary_text_rejected(self):
        invalid = (
            upload("empty.txt", b"", "text/plain"),
            upload("fake.pdf", b"%PDF-", "text/plain"),
            upload("evil.exe.pdf", b"%PDF-1.4", "application/pdf"),
            upload("bad.pdf", b"not-pdf", "application/pdf"),
            upload("binary.txt", b"a\x00b", "text/plain"),
        )
        for candidate in invalid:
            with self.subTest(candidate.name), self.assertRaises(ValidationError):
                validate_attachment(candidate)

    def test_active_and_macro_formats_are_rejected(self):
        cases = (
            upload("bad.svg", b"<svg/>", "image/svg+xml"),
            upload("bad.html", b"<html/>", "text/html"),
            upload("bad.zip", b"PK\x03\x04", "application/zip"),
            upload("bad.exe", b"MZ", "application/octet-stream"),
            upload("bad.docm", ooxml_bytes("docx"), "application/octet-stream"),
            upload("bad.xlsm", ooxml_bytes("xlsx"), "application/octet-stream"),
            upload("bad.xlsb", b"data", "application/octet-stream"),
            upload("macro.docx", ooxml_bytes("docx", macro=True), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            upload("macro.xls", bytes.fromhex("D0CF11E0A1B11AE1") + b"_VBA_PROJECT_CUR", "application/vnd.ms-excel"),
        )
        for candidate in cases:
            with self.subTest(candidate.name), self.assertRaises(ValidationError):
                validate_attachment(candidate)

    def test_zip_ratio_bomb_and_image_dimension_bomb_rejected(self):
        with self.assertRaises(ValidationError):
            validate_attachment(upload(
                "bomb.docx", ooxml_bytes("docx", ratio_bomb=True),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ))
        stream = io.BytesIO()
        Image.new("RGB", (6000, 5000), "white").save(stream, format="PNG")
        with self.assertRaises(ValidationError):
            validate_attachment(upload("large.png", stream.getvalue(), "image/png"))

    def test_name_is_basename_sanitized_and_storage_uses_uuid_without_public_url(self):
        metadata = validate_attachment(upload("../../<script>.pdf", b"%PDF-1.4", "application/pdf"))
        self.assertNotIn("/", metadata["safe_display_name"])
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message, name="visible.pdf")
        self.assertEqual(Path(attachment.file.name).stem, attachment.pk.hex)
        self.assertNotIn("visible", attachment.file.name)
        self.assertFalse(os.path.commonpath([attachment.file.path, self.private_tmp]) != self.private_tmp)
        with self.assertRaises(ValueError):
            private_ia_storage.url(attachment.file.name)

    def test_relation_rejects_message_from_other_conversation(self):
        first, _ = self.conversation()
        second = ConversacionIA.objects.create(user=self.owner, titulo="Other")
        other_message = MensajeIA.objects.create(
            conversacion=second, rol=MensajeIA.Rol.USUARIO, contenido="x"
        )
        attachment = AdjuntoIA(
            conversation=first, message=other_message, owner=self.owner,
            original_name="x.txt", safe_display_name="x.txt", declared_mime="text/plain",
            detected_mime="text/plain", extension=".txt", size_bytes=1, sha256="b" * 64,
        )
        with self.assertRaises(ValidationError):
            attachment.full_clean(exclude=("file",))

    @patch("intasa_ia.views.process_document_message.delay")
    @patch("intasa_ia.views.generar_respuesta_segura")
    def test_attachment_only_is_queued_without_web_openai_call(self, generate, delay):
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("intasa_ia:inicio"),
                {"pregunta": "", "adjuntos": upload("notes.txt", b"hello", "text/plain")},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        generate.assert_not_called()
        delay.assert_called_once()
        self.assertEqual(AdjuntoIA.objects.count(), 1)
        self.assertEqual(AdjuntoIA.objects.get().status, AdjuntoIA.Estado.UPLOADED)
        self.assertEqual(ProcesamientoMensajeIA.objects.get().status, ProcesamientoMensajeIA.Estado.QUEUED)
        self.assertContains(response, "En cola para procesar")

    @patch("intasa_ia.views.process_document_message.delay")
    @patch("intasa_ia.views.generar_respuesta_segura", return_value=RESULT)
    def test_text_and_attachment_is_queued_without_web_provider_call(self, generate, delay):
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("intasa_ia:inicio"),
                {"pregunta": "Resume mi idea", "adjuntos": upload("secret.txt", b"BINARY_SENTINEL", "text/plain")},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        generate.assert_not_called()
        delay.assert_called_once()
        self.assertNotIn("BINARY_SENTINEL", repr(delay.call_args))
        self.assertContains(response, "Procesando")

    @patch("intasa_ia.views.process_document_message.delay")
    @patch("intasa_ia.views.generar_respuesta_segura")
    def test_new_conversation_receives_exact_accumulated_attachment_list(self, generate, delay):
        self.client.force_login(self.owner)
        expected_names = ["a.txt", "c.txt", "d.txt"]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("intasa_ia:inicio"),
                {
                    "pregunta": "Analiza estos archivos",
                    "adjuntos": [
                        upload("a.txt", b"first", "text/plain"),
                        upload("c.txt", b"third", "text/plain"),
                        upload("d.txt", b"fourth", "text/plain"),
                    ],
                },
            )
        self.assertEqual(response.status_code, 302)
        conversation = ConversacionIA.objects.get()
        user_message = conversation.mensajes.get(rol=MensajeIA.Rol.USUARIO)
        self.assertEqual(
            list(user_message.adjuntos.order_by("created_at").values_list("original_name", flat=True)),
            expected_names,
        )
        self.assertEqual(user_message.adjuntos.count(), len(expected_names))
        generate.assert_not_called()
        delay.assert_called_once()

    @patch("intasa_ia.views.process_document_message.delay")
    @patch("intasa_ia.views.generar_respuesta_segura")
    def test_existing_conversation_receives_exact_attachment_only_list(self, generate, delay):
        conversation, original_message = self.conversation()
        self.client.force_login(self.owner)
        expected_names = ["one.txt", "two.txt", "three.txt"]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("intasa_ia:detalle", args=[conversation.pk]),
                {
                    "pregunta": "",
                    "adjuntos": [
                        upload("one.txt", b"one", "text/plain"),
                        upload("two.txt", b"two", "text/plain"),
                        upload("three.txt", b"three", "text/plain"),
                    ],
                },
            )
        self.assertEqual(response.status_code, 302)
        user_message = (
            conversation.mensajes.filter(rol=MensajeIA.Rol.USUARIO)
            .exclude(pk=original_message.pk)
            .get()
        )
        self.assertEqual(
            list(user_message.adjuntos.order_by("created_at").values_list("original_name", flat=True)),
            expected_names,
        )
        self.assertEqual(user_message.conversacion_id, conversation.pk)
        generate.assert_not_called()
        delay.assert_called_once()

    def test_invalid_batch_creates_neither_conversation_message_nor_file(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("intasa_ia:inicio"),
            {"pregunta": "x", "adjuntos": upload("bad.pdf", b"bad", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConversacionIA.objects.count(), 0)
        self.assertEqual(MensajeIA.objects.count(), 0)
        self.assertEqual(list(Path(self.private_tmp).rglob("*")), [])

    def test_second_storage_failure_rolls_back_database_and_cleans_first_file(self):
        self.client.force_login(self.owner)
        original_save = AdjuntoIA.save
        calls = {"count": 0}

        def fail_second(instance, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated storage failure")
            return original_save(instance, *args, **kwargs)

        with patch("intasa_ia.attachment_services.AdjuntoIA.save", new=fail_second):
            with self.assertRaises(OSError):
                self.client.post(
                    reverse("intasa_ia:inicio"),
                    {
                        "pregunta": "x",
                        "adjuntos": [
                            upload("one.txt", b"one", "text/plain"),
                            upload("two.txt", b"two", "text/plain"),
                        ],
                    },
                )
        self.assertEqual(ConversacionIA.objects.count(), 0)
        self.assertEqual(MensajeIA.objects.count(), 0)
        self.assertEqual(AdjuntoIA.objects.count(), 0)
        self.assertEqual([path for path in Path(self.private_tmp).rglob("*") if path.is_file()], [])

    def test_completely_empty_message_is_rejected(self):
        form = PreguntaIAForm(data={"pregunta": ""}, files={})
        self.assertFalse(form.is_valid())

    def test_download_permissions_headers_streaming_and_revocation(self):
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message)
        AccesoConversacionIA.objects.create(
            conversacion=conversation, user=self.shared, shared_by=self.owner
        )
        url = reverse("intasa_ia:descargar_adjunto", args=[attachment.pk])
        for user, status in (
            (self.owner, 200), (self.shared, 200), (self.outsider, 404),
            (self.staff, 404), (self.superuser, 404),
        ):
            with self.subTest(user.username):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, status)
                if status == 200:
                    self.assertTrue(response.streaming)
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertIn("no-store", response["Cache-Control"])
        conversation.accesos_compartidos.filter(user=self.shared).delete()
        self.client.force_login(self.shared)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_user_without_use_permission_cannot_download(self):
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message)
        no_permission = User.objects.create_user(username="att-no-permission")
        self.client.force_login(no_permission)
        response = self.client.get(
            reverse("intasa_ia:descargar_adjunto", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_shared_user_cannot_post_attachment(self):
        conversation, _ = self.conversation()
        AccesoConversacionIA.objects.create(
            conversacion=conversation, user=self.shared, shared_by=self.owner
        )
        self.client.force_login(self.shared)
        response = self.client.post(
            reverse("intasa_ia:detalle", args=[conversation.pk]),
            {"pregunta": "", "adjuntos": upload("a.txt", b"a", "text/plain")},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AdjuntoIA.objects.count(), 0)

    def test_delete_conversation_removes_record_and_physical_file_after_commit(self):
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message)
        path = attachment.file.path
        self.assertTrue(os.path.exists(path))
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("intasa_ia:eliminar_conversacion", args=[conversation.pk]), follow=True
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AdjuntoIA.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(os.path.exists(path))

    def test_delete_failure_registers_pending_purge_without_sensitive_content(self):
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message)
        self.client.force_login(self.owner)
        with patch.object(private_ia_storage, "delete", side_effect=OSError("secret path")):
            with patch(
                "intasa_ia.attachment_services.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                response = self.client.post(
                    reverse("intasa_ia:eliminar_conversacion", args=[conversation.pk]), follow=True
                )
        self.assertContains(response, "pendientes de purga")
        pending = PurgaAdjuntoIAPendiente.objects.get(attachment_id=attachment.pk)
        self.assertEqual(pending.error_code, "storage_delete_failed")
        self.assertNotIn("secret path", pending.error_code)

    def test_reconciliation_default_is_read_only(self):
        conversation, message = self.conversation()
        attachment = self.create_attachment(conversation, message)
        before = (AdjuntoIA.objects.count(), PurgaAdjuntoIAPendiente.objects.count())
        output = io.StringIO()
        call_command("reconcile_ia_attachments", stdout=output)
        self.assertIn("registered=1", output.getvalue())
        self.assertEqual(before, (AdjuntoIA.objects.count(), PurgaAdjuntoIAPendiente.objects.count()))
        self.assertTrue(os.path.exists(attachment.file.path))

    def test_template_has_both_multipart_forms_and_responsive_contract(self):
        template = Path(__file__).with_name("templates") / "intasa_ia" / "inicio.html"
        css = template.with_name("_responsive.css")
        source = template.read_text(encoding="utf-8")
        styles = css.read_text(encoding="utf-8")
        self.assertEqual(source.count('enctype="multipart/form-data"'), 2)
        self.assertEqual(source.count("data-ia-attachment-feedback"), 3)
        self.assertIn("Adjuntar archivos", source)
        self.assertIn("DataTransfer", source)
        self.assertIn("const selectedFiles = [];", source)
        self.assertIn("function handleSelection(event)", source)
        self.assertIn(
            '[file.name, file.size, file.type || "", file.lastModified || 0]',
            source,
        )
        self.assertIn("selectedFiles.push(file);", source)
        self.assertIn("selectedFiles.splice(index, 1);", source)
        self.assertIn('event.formData.delete(fieldName);', source)
        self.assertIn('event.formData.append(fieldName, file, file.name);', source)
        self.assertIn("installNextFallbackPicker", source)
        self.assertIn("const MAX_FILES = 5;", source)
        self.assertIn("const MAX_FILE_BYTES = 10 * 1048576;", source)
        self.assertIn("const MAX_TOTAL_BYTES = 25 * 1048576;", source)
        self.assertIn('selectedFiles.length + " de 5 archivos', source)
        self.assertIn("Este archivo ya está seleccionado.", source)
        self.assertNotIn('input.addEventListener("change", renderFiles)', source)
        self.assertIn("@media screen and (max-width: 767.98px)", styles)
        self.assertIn("@media screen and (min-width: 768px)", styles)
        self.assertIn("@media screen and (min-width: 1200px)", styles)
        self.assertIn("overflow-wrap: anywhere", styles)
        compose = Path(__file__).parents[2] / "infra" / "docker-compose.prod.yml"
        compose_source = compose.read_text(encoding="utf-8")
        caddy_source = (compose.parent / "caddy" / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("intasa_ia_private_data:/app/private_media/intasa_ia", compose_source)
        self.assertNotIn("private_media", caddy_source)

    def test_message_listing_query_count_does_not_grow_with_attachments(self):
        conversation, message = self.conversation()
        self.create_attachment(conversation, message, "first.pdf")
        self.client.force_login(self.owner)
        url = reverse("intasa_ia:detalle", args=[conversation.pk])
        with CaptureQueriesContext(connection) as first:
            self.client.get(url)
        for index in range(5):
            extra = MensajeIA.objects.create(
                conversacion=conversation,
                rol=MensajeIA.Rol.USUARIO,
                contenido=f"message {index}",
            )
            self.create_attachment(conversation, extra, f"extra-{index}.pdf")
        with CaptureQueriesContext(connection) as many:
            self.client.get(url)
        self.assertLessEqual(len(many), len(first) + 1)
