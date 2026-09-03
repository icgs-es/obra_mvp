from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from .models import Candidato, Candidatura, ProcesoSeleccion


class CandidaturaOriginListV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_origin_list_user",
            password="test-pass-123",
        )
        self.team = Team.objects.create(
            name="Empresa origen candidatura"
        )
        self.team.members.add(self.user)

        access = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        self.user.user_permissions.add(access)

        self.process = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Proceso origen",
            responsable=self.user,
            creado_por=self.user,
        )
        self.candidate = Candidato.objects.create(
            team=self.team,
            nombre_completo="Candidato Origen",
            email="origen@example.com",
            creado_por=self.user,
        )
        Candidatura.objects.create(
            proceso=self.process,
            candidato=self.candidate,
            responsable=self.user,
            origen=Candidatura.Origen.LINKEDIN,
            fecha_solicitud=timezone.localdate(),
            estado=Candidatura.Estado.RECIBIDO,
            creado_por=self.user,
        )

        self.client.force_login(self.user)

    def test_list_shows_origin_without_process_column_or_scroll(self):
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "RRHH_ORIGIN_COLUMN_V1",
            html=False,
        )
        self.assertContains(response, "<th>Origen</th>", html=True)
        self.assertContains(response, "LinkedIn")
        self.assertNotContains(response, "<th>Proceso</th>", html=True)
        self.assertNotContains(
            response,
            "rrhh-selection-table-scroll",
            html=False,
        )
