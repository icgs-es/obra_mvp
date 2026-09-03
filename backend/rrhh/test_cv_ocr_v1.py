import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from .forms import CandidaturaForm
from .models import Candidatura, ProcesoSeleccion
from .services.cv_ocr import extract_cv_fields


class CvFieldExtractionV1Tests(SimpleTestCase):
    def test_extracts_main_candidate_data(self):
        result = extract_cv_fields(
            """
            MARÍA DEL CARMEN RUIZ LÓPEZ
            Arquitecta técnica · Aparejadora
            Córdoba, España
            Teléfono: 612 345 678
            maria.ruiz@example.com
            https://www.linkedin.com/in/maria-ruiz
            PERFIL PROFESIONAL
            Arquitecta técnica con experiencia en dirección de ejecución.
            """,
            "CV_Maria_Ruiz.pdf",
        )
        fields = result["fields"]
        self.assertEqual(fields["nombre_completo"], "MARÍA DEL CARMEN RUIZ LÓPEZ")
        self.assertEqual(fields["telefono"], "612 345 678")
        self.assertEqual(fields["email"], "maria.ruiz@example.com")
        self.assertIn("linkedin.com/in/maria-ruiz", fields["linkedin_url"])
        self.assertIn("Arquitecta técnica", fields["perfil_profesional"])

    def test_filename_is_safe_fallback_for_name(self):
        result = extract_cv_fields(
            "Correo: candidato@example.com",
            "CV_Juan_Perez_Garcia.pdf",
        )
        self.assertEqual(
            result["fields"]["nombre_completo"],
            "Juan Perez Garcia",
        )


class CandidaturaDesdeCvV1Tests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rrhh-cv-ocr-v1-")
        self.media = tempfile.mkdtemp(prefix="rrhh-cv-media-v1-")
        self.override = override_settings(
            RRHH_CV_PENDING_DIR=self.tmp,
            MEDIA_ROOT=self.media,
        )
        self.override.enable()

        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_cv_user",
            password="test-pass-123",
        )
        self.responsable = User.objects.create_user(
            username="responsable_cv",
            password="test-pass-123",
        )
        self.other = User.objects.create_user(
            username="other_cv",
            password="test-pass-123",
        )
        self.team = Team.objects.create(name="Empresa CV")
        self.other_team = Team.objects.create(name="Otra empresa CV")
        self.team.members.add(self.user, self.responsable)
        self.other_team.members.add(self.other)

        permission = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        self.user.user_permissions.add(permission)
        self.responsable.user_permissions.add(permission)
        self.other.user_permissions.add(permission)

        self.proceso = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Técnico arquitectura",
            responsable=self.responsable,
            creado_por=self.user,
        )
        self.other_process = ProcesoSeleccion.objects.create(
            team=self.other_team,
            titulo="Proceso no visible",
            creado_por=self.other,
        )
        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.media, ignore_errors=True)

    def pdf(self):
        return SimpleUploadedFile(
            "curriculum_ana.pdf",
            b"%PDF-1.4\nCV TEST\n%%EOF",
            content_type="application/pdf",
        )

    def entry_url(self, process=None):
        return reverse(
            "rrhh:candidatura_desde_cv",
            kwargs={
                "proceso_pk": (process or self.proceso).pk,
            },
        )

    def preview_url(self, process=None):
        return reverse(
            "rrhh:candidatura_cv_preview",
            kwargs={
                "proceso_pk": (process or self.proceso).pk,
            },
        )

    def preview(self):
        with patch(
            "rrhh.services.cv_ocr.extract_pdf_text"
        ) as extract:
            extract.return_value = {
                "ok": True,
                "text": (
                    "ANA GARCÍA RUIZ\n"
                    "Arquitecta técnica\n"
                    "Teléfono 611 222 333\n"
                    "ana.garcia@example.com\n"
                    "Ciudad: Córdoba\n"
                ),
                "method": "direct_text",
                "ocr_used": False,
                "pages": 2,
                "error": "",
            }

            response = self.client.post(
                self.entry_url(),
                {
                    "_action": "extract",
                    "cv_pdf": self.pdf(),
                },
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["token"])
        return response

    def token_payload(self, token):
        return signing.loads(
            token,
            salt="rrhh-cv-ocr-v1",
            max_age=3600,
        )

    def test_get_is_available_for_authorized_team(self):
        response = self.client.get(
            reverse(
                "rrhh:candidatura_desde_cv",
                kwargs={"proceso_pk": self.proceso.pk},
            ),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsable:")
        self.assertContains(response, self.responsable.username)
        self.assertNotContains(
            response,
            'id="rrhh-cv-pdf-viewer"',
        )

    def test_other_team_process_is_hidden(self):
        response = self.client.get(
            reverse(
                "rrhh:candidatura_desde_cv",
                kwargs={"proceso_pk": self.other_process.pk},
            ),
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_form_inherits_process_responsible(self):
        form = CandidaturaForm(
            {
                "proceso": self.proceso.pk,
                "nombre_completo": "Ana Manual",
                "telefono": "",
                "email": "ana.manual@example.com",
                "ciudad": "",
                "perfil_profesional": "",
                "linkedin_url": "",
                "observaciones_candidato": "",
                "responsable": "",
                "origen": "OTRO",
                "fecha_solicitud": timezone.localdate().isoformat(),
                "estado": "RECIBIDO",
                "puntuacion": "",
                "fecha_proximo_contacto": "",
                "fecha_entrevista": "",
                "observaciones_revision": "",
                "observaciones_entrevista": "",
                "cv_archivo": "",
            },
            {"cv_fichero": self.pdf()},
            request_user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        candidatura = form.save()
        self.assertEqual(candidatura.responsable, self.responsable)

    def test_preview_renders_compact_form_and_pdf_viewer(self):
        preview = self.preview()
        token = preview.context["token"]

        self.assertContains(
            preview,
            'id="rrhh-cv-pdf-viewer"',
        )
        self.assertContains(
            preview,
            self.preview_url(),
        )
        self.assertContains(
            preview,
            "form-control-sm",
        )
        self.assertContains(
            preview,
            "rrhh-cv-top-card",
        )
        self.assertContains(
            preview,
            "rrhh-cv-viewer-card",
        )
        self.assertContains(
            preview,
            "Abrir PDF en otra pestaña",
        )
        self.assertEqual(
            preview.context["initial"]["email"],
            "ana.garcia@example.com",
        )
        self.assertIn(
            token,
            preview.content.decode("utf-8"),
        )

    def test_authorized_preview_serves_inline_pdf_sameorigin(self):
        preview = self.preview()
        token = preview.context["token"]

        response = self.client.get(
            self.preview_url(),
            {"token": token},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/pdf",
        )
        self.assertTrue(
            response["Content-Disposition"].startswith("inline;"),
        )
        self.assertEqual(
            response["X-Frame-Options"],
            "SAMEORIGIN",
        )
        self.assertIn(
            "no-store",
            response["Cache-Control"],
        )
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        # Cerrar solo el archivo, no HttpResponseBase: este último
        # emite request_finished y puede cerrar PostgreSQL en TestCase.
        if response.file_to_stream is not None:
            response.file_to_stream.close()

    def test_preview_token_is_tied_to_user(self):
        preview = self.preview()
        token = preview.context["token"]

        self.client.force_login(self.responsable)
        response = self.client.get(
            self.preview_url(),
            {"token": token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_token_cannot_be_used_for_other_process(self):
        preview = self.preview()
        token = preview.context["token"]

        response = self.client.get(
            self.preview_url(self.other_process),
            {"token": token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_tampered_preview_token_is_rejected(self):
        preview = self.preview()
        token = preview.context["token"] + "x"

        response = self.client.get(
            self.preview_url(),
            {"token": token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_expired_preview_token_is_rejected(self):
        preview = self.preview()
        payload = self.token_payload(
            preview.context["token"]
        )

        with patch(
            "django.core.signing.time.time",
            return_value=1_000,
        ):
            expired_token = signing.dumps(
                payload,
                salt="rrhh-cv-ocr-v1",
                compress=True,
            )

        response = self.client.get(
            self.preview_url(),
            {"token": expired_token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_pending_filename_is_rejected(self):
        preview = self.preview()
        payload = self.token_payload(
            preview.context["token"]
        )
        payload["pending_name"] = "../../curriculum.pdf"
        invalid_token = signing.dumps(
            payload,
            salt="rrhh-cv-ocr-v1",
            compress=True,
        )

        response = self.client.get(
            self.preview_url(),
            {"token": invalid_token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_pending_pdf_is_rejected(self):
        preview = self.preview()
        token = preview.context["token"]
        payload = self.token_payload(token)

        pending_path = (
            Path(self.tmp)
            / payload["pending_name"]
        )
        pending_path.unlink()

        response = self.client.get(
            self.preview_url(),
            {"token": token},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_validation_error_keeps_pdf_viewer_available(self):
        preview = self.preview()
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            {
                "_action": "confirm",
                "token": token,
                "nombre_completo": "",
                "telefono": "611 222 333",
                "email": "ana.garcia@example.com",
                "ciudad": "Córdoba",
                "perfil_profesional": "Arquitecta técnica",
                "linkedin_url": "",
                "observaciones_candidato": "",
                "origen": "OTRO",
                "fecha_solicitud": (
                    timezone.localdate().isoformat()
                ),
                "puntuacion": "4",
                "observaciones_revision": "",
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="rrhh-cv-pdf-viewer"',
        )

        pdf_response = self.client.get(
            self.preview_url(),
            {"token": token},
            secure=True,
        )
        self.assertEqual(pdf_response.status_code, 200)
        if pdf_response.file_to_stream is not None:
            pdf_response.file_to_stream.close()

    def test_preview_and_confirm_create_candidate_store_and_cleanup_pdf(self):
        preview = self.preview()
        token = preview.context["token"]
        payload = self.token_payload(token)
        pending_path = (
            Path(self.tmp)
            / payload["pending_name"]
        )
        self.assertTrue(pending_path.is_file())

        response = self.client.post(
            self.entry_url(),
            {
                "_action": "confirm",
                "token": token,
                "nombre_completo": "Ana García Ruiz",
                "telefono": "611 222 333",
                "email": "ana.garcia@example.com",
                "ciudad": "Córdoba",
                "perfil_profesional": "Arquitecta técnica",
                "linkedin_url": "",
                "observaciones_candidato": "",
                "origen": "OTRO",
                "fecha_solicitud": (
                    timezone.localdate().isoformat()
                ),
                "puntuacion": "4",
                "observaciones_revision": "Datos revisados.",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)

        candidatura = Candidatura.objects.get(
            candidato__email="ana.garcia@example.com"
        )
        self.assertEqual(candidatura.proceso, self.proceso)
        self.assertEqual(
            candidatura.responsable,
            self.responsable,
        )
        self.assertEqual(
            candidatura.estado,
            Candidatura.Estado.RECIBIDO,
        )
        self.assertEqual(candidatura.puntuacion, 4)
        self.assertTrue(candidatura.cv_fichero)
        self.assertTrue(
            candidatura.seguimientos.filter(
                tipo="ALTA"
            ).exists()
        )
        self.assertFalse(pending_path.exists())
