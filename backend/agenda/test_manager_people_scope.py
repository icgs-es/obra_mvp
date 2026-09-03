from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from agenda.access import user_can_view_event
from agenda.models import Calendar, Event
from usuarios.models import Team


class AgendaManagerPeopleScopeTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.team_a = Team.objects.create(
            name="Manager People Scope A"
        )
        self.team_b = Team.objects.create(
            name="Manager People Scope B"
        )

        self.actor = User.objects.create_user(
            username="manager_scope_actor"
        )
        self.manager = User.objects.create_user(
            username="manager_scope_gerencia"
        )
        self.ordinary = User.objects.create_user(
            username="manager_scope_ordinary"
        )

        self.actor.teams.add(self.team_b)
        self.manager.teams.add(self.team_a)
        self.ordinary.teams.add(self.team_a)

        gerencia, _ = Group.objects.get_or_create(
            name="Gerencia"
        )
        self.manager.groups.add(gerencia)

        calendar = Calendar.objects.create(
            nombre="Agenda privada actor",
            tipo="PERSONAL",
            owner=self.actor,
        )

        self.event = Event.objects.create(
            title="Evento privado de otro Team",
            calendar=calendar,
            start=timezone.now(),
            visibility=Event.Visibility.PRIVADA,
            team=self.team_b,
            created_by=self.actor,
        )

    def test_gerencia_can_view_private_event_across_team(self):
        self.assertTrue(
            user_can_view_event(
                self.manager,
                self.event,
                active_team_id="all",
            )
        )

    def test_active_company_does_not_hide_event_from_gerencia(self):
        self.assertTrue(
            user_can_view_event(
                self.manager,
                self.event,
                active_team_id=str(self.team_a.pk),
            )
        )

    def test_ordinary_user_cannot_view_private_event_of_other_user(self):
        self.assertFalse(
            user_can_view_event(
                self.ordinary,
                self.event,
                active_team_id="all",
            )
        )
