from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team

from .models import Candidato, Candidatura, ProcesoSeleccion


class CandidaturasFilteredPrintV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="rrhh_filtered_print_user",
            password="test-pass-123",
        )
        self.other_user = User.objects.create_user(
            username="rrhh_filtered_print_other",
            password="test-pass-123",
        )

        self.team = Team.objects.create(
            name="Empresa impresión RRHH"
        )
        self.other_team = Team.objects.create(
            name="Otra empresa impresión RRHH"
        )

        self.team.members.add(self.user)
        self.other_team.members.add(self.other_user)

        access = Permission.objects.get(
            codename="access_recruitment",
            content_type__app_label="rrhh",
        )
        self.user.user_permissions.add(access)
        self.other_user.user_permissions.add(access)

        self.process = ProcesoSeleccion.objects.create(
            team=self.team,
            titulo="Proceso impresión",
            responsable=self.user,
            creado_por=self.user,
        )
        self.other_process = ProcesoSeleccion.objects.create(
            team=self.other_team,
            titulo="Proceso ajeno impresión",
            responsable=self.other_user,
            creado_por=self.other_user,
        )

        linkedin_candidate = Candidato.objects.create(
            team=self.team,
            nombre_completo="Candidato LinkedIn Print",
            email="linkedin-print@example.com",
            creado_por=self.user,
        )
        web_candidate = Candidato.objects.create(
            team=self.team,
            nombre_completo="Candidato Web Print",
            email="web-print@example.com",
            creado_por=self.user,
        )
        foreign_candidate = Candidato.objects.create(
            team=self.other_team,
            nombre_completo="Candidato Ajeno Print",
            email="ajeno-print@example.com",
            creado_por=self.other_user,
        )

        Candidatura.objects.create(
            proceso=self.process,
            candidato=linkedin_candidate,
            responsable=self.user,
            origen=Candidatura.Origen.LINKEDIN,
            fecha_solicitud=timezone.localdate(),
            estado=Candidatura.Estado.RECIBIDO,
            creado_por=self.user,
        )
        Candidatura.objects.create(
            proceso=self.process,
            candidato=web_candidate,
            responsable=self.user,
            origen=Candidatura.Origen.WEB,
            fecha_solicitud=timezone.localdate(),
            estado=Candidatura.Estado.DESCARTADO,
            creado_por=self.user,
        )
        Candidatura.objects.create(
            proceso=self.other_process,
            candidato=foreign_candidate,
            responsable=self.other_user,
            origen=Candidatura.Origen.LINKEDIN,
            fecha_solicitud=timezone.localdate(),
            estado=Candidatura.Estado.RECIBIDO,
            creado_por=self.other_user,
        )

        self.client.force_login(self.user)

    def test_list_has_print_button_using_same_get_form(self):
        response = self.client.get(
            reverse("rrhh:seleccion_personal_list"),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imprimir PDF")
        self.assertContains(
            response,
            reverse("rrhh:seleccion_personal_print"),
        )
        self.assertContains(
            response,
            'formtarget="_blank"',
            html=False,
        )

    def test_print_applies_origin_filter_and_team_isolation(self):
        response = self.client.get(
            reverse("rrhh:seleccion_personal_print"),
            {"origen": Candidatura.Origen.LINKEDIN},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Candidato LinkedIn Print")
        self.assertNotContains(response, "Candidato Web Print")
        self.assertNotContains(response, "Candidato Ajeno Print")
        self.assertContains(response, "Total: 1 candidatura")
        self.assertContains(response, "A4 landscape")
        self.assertContains(response, "window.print()")

    def test_print_contains_no_candidate_action_buttons(self):
        response = self.client.get(
            reverse("rrhh:seleccion_personal_print"),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Quitar PDF")
        self.assertNotContains(response, "Eliminar candidatura")
        self.assertNotContains(response, "Editar")
