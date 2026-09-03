import hashlib
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from .models import (
    Candidato,
    Candidatura,
    CandidaturaSeguimiento,
    ProcesoSeleccion,
)


class CvFastLoadDuplicateDeleteV1Tests(TestCase):
    def setUp(self):
        self.pending = tempfile.mkdtemp(
            prefix="rrhh-fast-pending-"
        )
        self.media = tempfile.mkdtemp(
            prefix="rrhh-fast-media-"
        )
        self.override = override_settings(
            RRHH_CV_PENDING_DIR=self.pending,
            MEDIA_ROOT=self.media,
        )
        self.override.enable()

        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_fast_user",
            password="test-pass-123",
        )
        self.deleter = User.objects.create_user(
            username="rrhh_fast_deleter",
            password="test-pass-123",
        )
        self.other = User.objects.create_user(
            username="rrhh_fast_other",
            password="test-pass-123",
        )

        self.team = Team.objects.create(
            name="Empresa carga rápida"
        )
        self.other_team = Team.objects.create(
            name="Otra empresa carga rápida"
        )
        self.team.members.add(self.user, self.deleter)
        self.other_team.members.add(self.other)

        access = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        delete = Permission.objects.get(
            codename="delete_candidatura",
            content_type__app_label="rrhh",
        )

        self.user.user_permissions.add(access)
        self.deleter.user_permissions.add(access, delete)
        self.other.user_permissions.add(access)

        self.process = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Arquitectura rápida",
            responsable=self.user,
            creado_por=self.user,
        )
        self.second_process = (
            ProcesoSeleccion.objects.create(
                team=self.team,
                titulo="Segundo proceso",
                responsable=self.user,
                creado_por=self.user,
            )
        )
        self.other_process = (
            ProcesoSeleccion.objects.create(
                team=self.other_team,
                titulo="Proceso oculto",
                creado_por=self.other,
            )
        )

        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.pending, ignore_errors=True)
        shutil.rmtree(self.media, ignore_errors=True)

    def entry_url(self, process=None):
        return reverse(
            "rrhh:candidatura_desde_cv",
            kwargs={
                "proceso_pk": (process or self.process).pk,
            },
        )

    def preview(
        self,
        *,
        name="Ana García Ruiz",
        email="ana@example.com",
        phone="611222333",
        filename="CV_Ana_Garcia.pdf",
        pdf_bytes=b"%PDF-1.4\nFAST TEST\n%%EOF",
    ):
        text = (
            f"{name}\n"
            "Arquitecta técnica\n"
            f"Teléfono: {phone}\n"
            f"{email}\n"
            "Ciudad: Córdoba\n"
        )

        with patch(
            "rrhh.services.cv_ocr.extract_pdf_text"
        ) as extract:
            extract.return_value = {
                "ok": True,
                "text": text,
                "method": "direct_text",
                "ocr_used": False,
                "pages": 1,
                "error": "",
            }
            response = self.client.post(
                self.entry_url(),
                {
                    "_action": "extract",
                    "cv_pdf": SimpleUploadedFile(
                        filename,
                        pdf_bytes,
                        content_type="application/pdf",
                    ),
                },
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["token"])
        return response

    def confirm_data(
        self,
        token,
        *,
        name="Ana García Ruiz",
        email="ana@example.com",
        phone="611222333",
        after_save="next",
        allow_duplicate=False,
    ):
        data = {
            "_action": "confirm",
            "token": token,
            "nombre_completo": name,
            "telefono": phone,
            "email": email,
            "ciudad": "Córdoba",
            "perfil_profesional": "Arquitecta técnica",
            "linkedin_url": "",
            "observaciones_candidato": "",
            "origen": "OTRO",
            "fecha_solicitud": (
                timezone.localdate().isoformat()
            ),
            "puntuacion": "",
            "observaciones_revision": "",
            "after_save": after_save,
        }
        if allow_duplicate:
            data["allow_duplicate"] = "1"
        return data

    def create_application(
        self,
        *,
        process=None,
        name="Persona existente",
        email="existente@example.com",
        phone="600000000",
        pdf_bytes=b"%PDF-1.4\nEXISTING\n%%EOF",
    ):
        candidate = Candidato.objects.create(
            team=(process or self.process).team,
            nombre_completo=name,
            email=email,
            telefono=phone,
            creado_por=self.user,
        )
        application = Candidatura.objects.create(
            proceso=process or self.process,
            candidato=candidate,
            responsable=self.user,
            creado_por=self.user,
            cv_nombre_original="curriculum_existente.pdf",
            cv_sha256=hashlib.sha256(
                pdf_bytes
            ).hexdigest(),
        )
        application.cv_fichero.save(
            "curriculum_existente.pdf",
            ContentFile(pdf_bytes),
            save=True,
        )
        return application

    def test_list_is_compact_and_has_fast_load_actions(self):
        application = self.create_application()

        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rrhh-compact-table")
        self.assertContains(response, "table-sm")
        self.assertContains(response, "Carga rápida")
        self.assertContains(response, application.candidato.nombre_completo)

    def test_save_and_load_next_redirects_to_same_process(self):
        preview = self.preview()
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(token, after_save="next"),
            secure=True,
        )

        self.assertRedirects(
            response,
            self.entry_url(),
            fetch_redirect_response=False,
        )
        application = Candidatura.objects.get(
            candidato__email="ana@example.com"
        )
        self.assertEqual(len(application.cv_sha256), 64)
        self.assertTrue(application.cv_fichero)

    def test_save_and_view_redirects_to_detail(self):
        preview = self.preview(
            email="detalle@example.com",
            phone="622333444",
        )
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(
                token,
                email="detalle@example.com",
                phone="622333444",
                after_save="detail",
            ),
            secure=True,
        )

        application = Candidatura.objects.get(
            candidato__email="detalle@example.com"
        )
        self.assertRedirects(
            response,
            reverse(
                "rrhh:candidatura_detail",
                kwargs={"pk": application.pk},
            ),
            fetch_redirect_response=False,
        )

    def test_same_email_blocks_without_explicit_override(self):
        self.create_application(
            email="repetido@example.com",
            phone="600111222",
        )
        preview = self.preview(
            email="repetido@example.com",
            phone="699888777",
            pdf_bytes=b"%PDF-1.4\nDIFFERENT\n%%EOF",
        )
        token = preview.context["token"]
        before = Candidatura.objects.count()

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(
                token,
                email="repetido@example.com",
                phone="699888777",
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Posible candidatura repetida")
        self.assertContains(response, "mismo correo")
        self.assertEqual(Candidatura.objects.count(), before)

    def test_duplicate_can_be_forced_after_explicit_confirmation(self):
        self.create_application(
            email="forzado@example.com",
            phone="600222333",
        )
        preview = self.preview(
            email="forzado@example.com",
            phone="699222333",
            pdf_bytes=b"%PDF-1.4\nFORCED\n%%EOF",
        )
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(
                token,
                email="forzado@example.com",
                phone="699222333",
                allow_duplicate=True,
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Candidatura.objects.filter(
                proceso=self.process
            ).count(),
            2,
        )

    def test_identical_pdf_blocks_even_with_different_contact_data(self):
        pdf_bytes = b"%PDF-1.4\nIDENTICAL\n%%EOF"
        self.create_application(
            email="original@example.com",
            phone="600333444",
            pdf_bytes=pdf_bytes,
        )
        preview = self.preview(
            name="Otra Persona",
            email="otra@example.com",
            phone="699333444",
            pdf_bytes=pdf_bytes,
        )
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(
                token,
                name="Otra Persona",
                email="otra@example.com",
                phone="699333444",
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PDF idéntico")
        self.assertEqual(
            Candidatura.objects.filter(
                proceso=self.process
            ).count(),
            1,
        )

    def test_candidate_is_reused_across_different_process(self):
        existing = self.create_application(
            process=self.second_process,
            name="Candidata reutilizable",
            email="reutilizable@example.com",
            phone="633444555",
        )
        candidate_id = existing.candidato_id
        before_candidates = Candidato.objects.count()

        preview = self.preview(
            name="Candidata reutilizable",
            email="reutilizable@example.com",
            phone="633444555",
            pdf_bytes=b"%PDF-1.4\nSECOND PROCESS\n%%EOF",
        )
        token = preview.context["token"]

        response = self.client.post(
            self.entry_url(),
            self.confirm_data(
                token,
                name="Candidata reutilizable",
                email="reutilizable@example.com",
                phone="633444555",
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        created = Candidatura.objects.get(
            proceso=self.process
        )
        self.assertEqual(created.candidato_id, candidate_id)
        self.assertEqual(
            Candidato.objects.count(),
            before_candidates,
        )

    def test_manual_form_rejects_identical_pdf_in_same_process(self):
        pdf_bytes = b"%PDF-1.4\nMANUAL DUPLICATE\n%%EOF"
        self.create_application(
            email="manual-original@example.com",
            phone="600555666",
            pdf_bytes=pdf_bytes,
        )

        response = self.client.post(
            reverse("rrhh:candidatura_create"),
            {
                "proceso": self.process.pk,
                "nombre_completo": "Manual duplicado",
                "telefono": "699555666",
                "email": "manual-nuevo@example.com",
                "ciudad": "Córdoba",
                "perfil_profesional": "Arquitecta",
                "linkedin_url": "",
                "observaciones_candidato": "",
                "responsable": self.user.pk,
                "origen": "OTRO",
                "fecha_solicitud": (
                    timezone.localdate().isoformat()
                ),
                "estado": "RECIBIDO",
                "puntuacion": "",
                "fecha_proximo_contacto": "",
                "fecha_entrevista": "",
                "observaciones_revision": "",
                "observaciones_entrevista": "",
                "cv_archivo": "",
                "cv_fichero": SimpleUploadedFile(
                    "manual-duplicado.pdf",
                    pdf_bytes,
                    content_type="application/pdf",
                ),
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Este PDF ya está asociado a otra candidatura",
        )
        self.assertFalse(
            Candidato.objects.filter(
                email="manual-nuevo@example.com"
            ).exists()
        )

    def test_remove_cv_clears_reference_and_deletes_physical_file(self):
        application = self.create_application()
        path = Path(application.cv_fichero.path)
        self.assertTrue(path.is_file())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "rrhh:candidatura_cv_remove",
                    kwargs={"pk": application.pk},
                ),
                secure=True,
            )

        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertFalse(application.cv_fichero)
        self.assertEqual(application.cv_sha256, "")
        self.assertFalse(path.exists())

    def test_delete_requires_delete_permission(self):
        application = self.create_application()

        response = self.client.post(
            reverse(
                "rrhh:candidatura_delete",
                kwargs={"pk": application.pk},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Candidatura.objects.filter(
                pk=application.pk
            ).exists()
        )

    def test_delete_removes_application_file_and_orphan_candidate(self):
        application = self.create_application()
        application_id = application.pk
        candidate_id = application.candidato_id
        path = Path(application.cv_fichero.path)

        self.client.force_login(self.deleter)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "rrhh:candidatura_delete",
                    kwargs={"pk": application.pk},
                ),
                secure=True,
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Candidatura.objects.filter(
                pk=application_id
            ).exists()
        )
        self.assertFalse(
            Candidato.objects.filter(
                pk=candidate_id
            ).exists()
        )
        self.assertFalse(path.exists())

    def test_delete_preserves_candidate_with_other_application(self):
        application = self.create_application()
        candidate = application.candidato
        Candidatura.objects.create(
            proceso=self.second_process,
            candidato=candidate,
            responsable=self.user,
            creado_por=self.user,
        )

        self.client.force_login(self.deleter)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "rrhh:candidatura_delete",
                    kwargs={"pk": application.pk},
                ),
                secure=True,
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Candidato.objects.filter(
                pk=candidate.pk
            ).exists()
        )

    def test_delete_is_hidden_across_teams(self):
        other_candidate = Candidato.objects.create(
            team=self.other_team,
            nombre_completo="No visible",
            creado_por=self.other,
        )
        other_application = Candidatura.objects.create(
            proceso=self.other_process,
            candidato=other_candidate,
            creado_por=self.other,
        )

        self.client.force_login(self.deleter)
        response = self.client.post(
            reverse(
                "rrhh:candidatura_delete",
                kwargs={"pk": other_application.pk},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Candidatura.objects.filter(
                pk=other_application.pk
            ).exists()
        )
