from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from usuarios.models import Team

from .models import Tarea


User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class TareasFlowTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(
            name="Tareas Team A",
        )

        self.team_b = Team.objects.create(
            name="INVERADRIDE",
        )

        self.creator = User.objects.create_user(
            username="creator",
            password="x",
        )

        self.assigned = User.objects.create_user(
            username="assigned",
            password="x",
        )

        self.member = User.objects.create_user(
            username="member",
            password="x",
        )

        self.other_team_user = (
            User.objects.create_user(
                username="other-team",
                password="x",
            )
        )

        self.creator.teams.add(
            self.team_a
        )

        self.assigned.teams.add(
            self.team_a
        )

        self.member.teams.add(
            self.team_a
        )

        self.other_team_user.teams.add(
            self.team_b
        )

        self.login_as(
            self.creator,
            self.team_a.pk,
        )

    def login_as(
        self,
        user,
        active_team_id,
    ):
        self.client.force_login(user)

        session = self.client.session
        session["active_team_id"] = str(
            active_team_id
        )

        # El middleware global inicializa una sesión nueva
        # en "Todas sus empresas". Esta marca representa
        # que el usuario ya pasó por dicha inicialización
        # y seleccionó expresamente una empresa.
        session[
            "_gestion_default_todas_empresas_user_id"
        ] = str(user.pk)

        session.save()

    def task_payload(
        self,
        *,
        title="Primera",
        state="pendiente",
        visibility="privada",
        assigned=None,
    ):
        data = {
            "titulo": title,
            "descripcion": "Descripción",
            "estado": state,
            "prioridad": "media",
            "etiquetas": "x,y,y",
            "visibilidad": visibility,
        }

        if assigned is not None:
            data["asignados"] = [
                user.pk
                for user in assigned
            ]

        return data

    def test_create_task_and_list(self):
        data = self.task_payload()
        data["team"] = str(self.team_a.pk)
        response = self.client.post(
            reverse("tareas:create"),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        task = Tarea.objects.get(
            titulo="Primera"
        )

        self.assertEqual(
            task.team,
            self.team_a,
        )

        self.assertEqual(
            task.creador,
            self.creator,
        )

        self.assertTrue(
            task.asignados.filter(
                pk=self.creator.pk
            ).exists()
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Primera",
        )

    def test_visibility_choices_enforced(self):
        data = self.task_payload(
            title="VisBad",
        ) | {
            "team": str(self.team_a.pk),
            "visibilidad": "zzz",
        }
        response = self.client.post(
            reverse("tareas:create"),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        errors = (
            response.context["form"]
            .errors
            .as_data()
        )

        self.assertEqual(
            errors["visibilidad"][0].code,
            "invalid_choice",
        )

        self.assertFalse(
            Tarea.objects.filter(
                titulo="VisBad"
            ).exists()
        )

    def test_create_requires_explicit_team(self):
        self.login_as(
            self.creator,
            "all",
        )

        response = self.client.post(
            reverse("tareas:create"),
            data=self.task_payload(
                title="Sin empresa",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Selecciona una empresa concreta "
                "antes de crear la tarea."
            ),
        )

        self.assertFalse(
            Tarea.objects.filter(
                titulo="Sin empresa"
            ).exists()
        )

    def test_cross_team_task_isolated(self):
        task = Tarea.objects.create(
            team=self.team_b,
            titulo="Otra empresa",
            creador=self.other_team_user,
            visibilidad="global",
        )

        task.asignados.add(
            self.other_team_user
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertNotContains(
            response,
            "Otra empresa",
        )

        response = self.client.get(
            reverse(
                "tareas:update",
                args=[task.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_staff_without_functional_permission_cannot_edit_other_task(self):
        task = Tarea.objects.create(
            team=self.team_a,
            titulo="Tarea de otro usuario",
            creador=self.creator,
            visibilidad="depto",
        )
        staff = User.objects.create_user(
            username="task_staff_without_functional_permission",
            password="x",
            is_staff=True,
        )
        staff.teams.add(self.team_a)
        self.login_as(staff, self.team_a.pk)

        response = self.client.get(reverse("tareas:update", args=[task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_create_rejects_cross_team_assignee_from_manipulated_team(self):
        self.creator.teams.add(self.team_b)
        data = self.task_payload(
            title="Cruce manipulado",
            assigned=[self.assigned],
        )
        data["team"] = str(self.team_b.pk)

        response = self.client.post(reverse("tareas:create"), data=data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("asignados", response.context["form"].errors)
        self.assertFalse(
            Tarea.objects.filter(titulo="Cruce manipulado").exists()
        )

    def test_create_with_selected_team_when_global_selector_is_all(self):
        self.creator.teams.add(self.team_b)
        self.login_as(self.creator, "all")
        data = self.task_payload(
            title="Tarea INVERADRIDE",
            assigned=[self.other_team_user],
        )
        data["team"] = str(self.team_b.pk)

        response = self.client.post(reverse("tareas:create"), data=data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Tarea.objects.get(titulo="Tarea INVERADRIDE").team,
            self.team_b,
        )

    def test_create_with_authorized_team_different_from_active_team(self):
        self.creator.teams.add(self.team_b)
        data = self.task_payload(
            title="Empresa distinta de la activa",
            assigned=[self.other_team_user],
        )
        data["team"] = str(self.team_b.pk)

        response = self.client.post(reverse("tareas:create"), data=data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Tarea.objects.get(
                titulo="Empresa distinta de la activa"
            ).team,
            self.team_b,
        )

    def test_create_rejects_unauthorized_selected_team(self):
        self.login_as(self.creator, "all")
        data = self.task_payload(title="Empresa ajena")
        data["team"] = str(self.team_b.pk)

        response = self.client.post(reverse("tareas:create"), data=data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("team", response.context["form"].errors)
        self.assertFalse(Tarea.objects.filter(titulo="Empresa ajena").exists())

    def test_private_task_creator_or_assigned_only(
        self,
    ):
        task = Tarea.objects.create(
            team=self.team_a,
            titulo="Privada",
            creador=self.creator,
            visibilidad="privada",
        )

        task.asignados.add(
            self.assigned
        )

        self.login_as(
            self.assigned,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertContains(
            response,
            "Privada",
        )

        data = self.task_payload(
            title="Privada",
            state="hecha",
            assigned=[
                self.creator,
                self.assigned,
            ],
        )
        data["team"] = str(self.team_a.pk)
        response = self.client.post(
            reverse(
                "tareas:update",
                args=[task.pk],
            ),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        task.refresh_from_db()

        self.assertEqual(
            task.estado,
            "hecha",
        )

        self.login_as(
            self.member,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertNotContains(
            response,
            "Privada",
        )

        response = self.client.get(
            reverse(
                "tareas:update",
                args=[task.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_department_visible_but_edit_restricted(
        self,
    ):
        task = Tarea.objects.create(
            team=self.team_a,
            titulo="Departamento",
            creador=self.creator,
            visibilidad="depto",
        )

        task.asignados.add(
            self.creator
        )

        self.login_as(
            self.member,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertContains(
            response,
            "Departamento",
        )

        response = self.client.get(
            reverse(
                "tareas:update",
                args=[task.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_legacy_task_only_creator_or_assigned(
        self,
    ):
        task = Tarea.objects.create(
            team=None,
            titulo="Histórica sin empresa",
            creador=self.creator,
            visibilidad="global",
        )

        task.asignados.add(
            self.assigned
        )

        self.login_as(
            self.member,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertNotContains(
            response,
            "Histórica sin empresa",
        )

        self.login_as(
            self.assigned,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("tareas:list")
        )

        self.assertContains(
            response,
            "Histórica sin empresa",
        )

    def test_assignee_queryset_is_team_scoped(
        self,
    ):
        response = self.client.get(
            reverse("tareas:create")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        queryset = (
            response.context["form"]
            .fields["asignados"]
            .queryset
        )

        ids = set(
            queryset.values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            ids,
            {
                self.creator.pk,
                self.assigned.pk,
                self.member.pk,
            },
        )

        self.assertNotIn(
            self.other_team_user.pk,
            ids,
        )
