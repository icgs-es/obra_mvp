from django.urls import reverse

from agenda.models import Event
from agenda.test_views_scope import (
    AgendaEndpointScopeTests,
)


class AgendaEventCompanySelectorTests(
    AgendaEndpointScopeTests
):
    def selected_team(self):
        return (
            self.user_a.teams
            .order_by("pk")
            .first()
        )

    def test_global_scope_exposes_company_selector(
        self,
    ):
        self.login(
            self.user_a,
            "all",
        )

        team = self.selected_team()

        self.assertIsNotNone(team)

        response = self.client.get(
            reverse("agenda:create")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            'name="team"',
        )

        self.assertContains(
            response,
            "Selecciona una empresa",
        )

        self.assertContains(
            response,
            team.name,
        )

    def test_concrete_scope_and_edit_show_company(
        self,
    ):
        team = self.selected_team()

        self.assertIsNotNone(team)

        self.login(
            self.user_a,
            str(team.pk),
        )

        create_response = self.client.get(
            reverse("agenda:create")
        )

        self.assertEqual(
            create_response.status_code,
            200,
        )

        self.assertContains(
            create_response,
            'id="id_team_display"',
        )

        self.assertContains(
            create_response,
            team.name,
        )

        payload = self.event_form_payload(
            title=(
                "Evento empresa visible "
                "en edición"
            ),
            calendar=(
                self.private_a_calendar
            ),
            visibility="PRIVADA",
        )

        response = self.client.post(
            reverse("agenda:create"),
            data=payload,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        event = Event.objects.get(
            title=(
                "Evento empresa visible "
                "en edición"
            )
        )

        edit_response = self.client.get(
            reverse(
                "agenda:edit",
                args=[event.pk],
            )
        )

        self.assertEqual(
            edit_response.status_code,
            200,
        )

        self.assertContains(
            edit_response,
            'id="id_team_display"',
        )

        self.assertContains(
            edit_response,
            team.name,
        )

        self.assertContains(
            edit_response,
            "Empresa",
        )

        self.assertContains(
            edit_response,
            "readonly",
        )

        self.assertNotContains(
            edit_response,
            'name="team"',
        )

    def test_global_scope_selected_company_creates_event(
        self,
    ):
        self.login(
            self.user_a,
            "all",
        )

        team = self.selected_team()

        self.assertIsNotNone(team)

        payload = self.event_form_payload(
            title=(
                "Evento con empresa "
                "seleccionada"
            ),
            calendar=(
                self.private_a_calendar
            ),
            visibility="PRIVADA",
        )

        payload["team"] = str(
            team.pk
        )

        response = self.client.post(
            reverse("agenda:create"),
            data=payload,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        event = Event.objects.get(
            title=(
                "Evento con empresa "
                "seleccionada"
            )
        )

        self.assertEqual(
            event.team_id,
            team.pk,
        )

        self.assertEqual(
            event.created_by_id,
            self.user_a.pk,
        )


for _name in dir(
    AgendaEndpointScopeTests
):
    if _name.startswith("test_"):
        setattr(
            AgendaEventCompanySelectorTests,
            _name,
            None,
        )

del _name
