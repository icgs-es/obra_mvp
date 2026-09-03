import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
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


class SeleccionPersonalV1Tests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="rrhh-selection-test-")
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_user",
            password="test-pass-123",
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            password="test-pass-123",
        )
        self.team = Team.objects.create(name="Empresa RRHH")
        self.other_team = Team.objects.create(name="Otra empresa")
        self.team.members.add(self.user)
        self.other_team.members.add(self.other_user)

        permission = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        self.user.user_permissions.add(permission)

        self.proceso = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Arquitecto técnico",
            area="ARQUITECTURA",
            creado_por=self.user,
        )
        self.candidato = Candidato.objects.create(
            team=self.team,
            nombre_completo="Candidato Uno",
            email="candidato@example.com",
            creado_por=self.user,
        )
        self.candidatura = Candidatura.objects.create(
            proceso=self.proceso,
            candidato=self.candidato,
            creado_por=self.user,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_permission_required(self):
        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )
        self.assertEqual(response.status_code, 403)

    def test_authorized_user_can_open_list(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Candidato Uno")
        self.assertContains(response, "Arquitecto técnico")

    def test_team_isolation(self):
        other_process = ProcesoSeleccion.objects.create(
            team=self.other_team,
            titulo="No visible",
            creado_por=self.other_user,
        )
        other_candidate = Candidato.objects.create(
            team=self.other_team,
            nombre_completo="Candidato Oculto",
            creado_por=self.other_user,
        )
        Candidatura.objects.create(
            proceso=other_process,
            candidato=other_candidate,
            creado_por=self.other_user,
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )
        self.assertNotContains(response, "Candidato Oculto")

    def test_cross_team_candidate_is_invalid(self):
        foreign_candidate = Candidato.objects.create(
            team=self.other_team,
            nombre_completo="Otra empresa",
        )
        candidature = Candidatura(
            proceso=self.proceso,
            candidato=foreign_candidate,
        )
        with self.assertRaises(ValidationError):
            candidature.full_clean()

    def test_create_application_with_pdf(self):
        self.client.force_login(self.user)
        pdf = SimpleUploadedFile(
            "curriculum.pdf",
            b"%PDF-1.4 test",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("rrhh:candidatura_create"),
            {
                "proceso": self.proceso.pk,
                "nombre_completo": "Nueva Persona",
                "telefono": "600000000",
                "email": "nueva@example.com",
                "ciudad": "Córdoba",
                "perfil_profesional": "Arquitecta",
                "linkedin_url": "",
                "observaciones_candidato": "",
                "responsable": self.user.pk,
                "origen": "LINKEDIN",
                "fecha_solicitud": timezone.localdate().isoformat(),
                "estado": "RECIBIDO",
                "puntuacion": "4",
                "fecha_proximo_contacto": "",
                "fecha_entrevista": "",
                "observaciones_revision": "Buen perfil",
                "observaciones_entrevista": "",
                "cv_archivo": "",
                "cv_fichero": pdf,
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        created = Candidatura.objects.get(candidato__email="nueva@example.com")
        self.assertTrue(created.cv_fichero)
        self.assertEqual(created.puntuacion, 4)
        self.assertTrue(created.seguimientos.filter(tipo="ALTA").exists())

    def test_add_interview_followup_updates_application(self):
        self.client.force_login(self.user)
        interview = timezone.localtime() + timedelta(days=2)
        response = self.client.post(
            reverse(
                "rrhh:candidatura_seguimiento_add",
                kwargs={"pk": self.candidatura.pk},
            ),
            {
                "tipo": "ENTREVISTA",
                "fecha": interview.strftime("%Y-%m-%dT%H:%M"),
                "completado": "",
                "notas": "Entrevista inicial",
                "resultado": "",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.candidatura.refresh_from_db()
        self.assertEqual(
            self.candidatura.estado,
            Candidatura.Estado.ENTREVISTA_PROGRAMADA,
        )
        self.assertIsNotNone(self.candidatura.fecha_entrevista)
        self.assertTrue(
            CandidaturaSeguimiento.objects.filter(
                candidatura=self.candidatura,
                tipo="ENTREVISTA",
            ).exists()
        )
