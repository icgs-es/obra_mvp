from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from .models import Candidato, Candidatura, ProcesoSeleccion


class CandidaturaDateDisplayAndDiscardedRowV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_date_display_user",
            password="test-pass-123",
        )
        self.team = Team.objects.create(
            name="Empresa fechas candidatura"
        )
        self.team.members.add(self.user)

        access = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        self.user.user_permissions.add(access)

        self.process = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Proceso fechas",
            responsable=self.user,
            creado_por=self.user,
        )
        self.candidate = Candidato.objects.create(
            team=self.team,
            nombre_completo="Candidato Fechas",
            email="fechas@example.com",
            creado_por=self.user,
        )
        self.application = Candidatura.objects.create(
            proceso=self.process,
            candidato=self.candidate,
            responsable=self.user,
            origen=Candidatura.Origen.OTRO,
            fecha_solicitud=date(2026, 7, 24),
            fecha_proximo_contacto=timezone.make_aware(
                datetime(2026, 7, 25, 9, 30)
            ),
            fecha_entrevista=timezone.make_aware(
                datetime(2026, 7, 26, 16, 45)
            ),
            estado=Candidatura.Estado.DESCARTADO,
            creado_por=self.user,
        )

        self.client.force_login(self.user)

    def test_edit_form_renders_iso_date_and_datetime_values(self):
        response = self.client.get(
            reverse(
                "rrhh:candidatura_edit",
                kwargs={"pk": self.application.pk},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'name="fecha_solicitud"',
            html=False,
        )
        self.assertContains(
            response,
            'value="2026-07-24"',
            html=False,
        )
        self.assertContains(
            response,
            'value="2026-07-25T09:30"',
            html=False,
        )
        self.assertContains(
            response,
            'value="2026-07-26T16:45"',
            html=False,
        )

    def test_discarded_application_has_soft_grey_row(self):
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "RRHH_DISCARDED_ROW_VISUAL_V1",
            html=False,
        )
        self.assertContains(
            response,
            'class="rrhh-row-discarded"',
            html=False,
        )
        self.assertContains(response, "Descartado")
