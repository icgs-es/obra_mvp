import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Team
from tareas.models import Tarea

from .models import Calendar, Event


User = get_user_model()


class IntegratedAgendaV1Tests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="INTASA Agenda V1")
        self.other_team = Team.objects.create(name="Otra empresa")
        self.user = User.objects.create_user(username="agenda_v1", password="x")
        self.other = User.objects.create_user(username="agenda_v1_other", password="x")
        self.user.teams.add(self.team)
        self.other.teams.add(self.other_team)
        self.calendar = Calendar.objects.create(nombre="Personal", tipo="PERSONAL", owner=self.user)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_team_id"] = str(self.team.pk)
        session.save()

    def test_feed_integrates_tasks_and_events_without_cross_company_leak(self):
        now = timezone.now().replace(second=0, microsecond=0)
        event = Event.objects.create(
            title="Evento integrado", calendar=self.calendar, start=now,
            end=now + dt.timedelta(hours=1), created_by=self.user,
            team=self.team, visibility=Event.Visibility.PRIVADA,
        )
        task = Tarea.objects.create(
            titulo="Tarea integrada", creador=self.user, team=self.team,
            inicio_programado=now, fin_programado=now + dt.timedelta(hours=2),
        )
        task.asignados.add(self.user)
        hidden = Tarea.objects.create(
            titulo="No filtrar", creador=self.other, team=self.other_team,
            inicio_programado=now,
        )
        hidden.asignados.add(self.other)

        response = self.client.get(reverse("agenda:api_events"), {
            "start": (now - dt.timedelta(days=1)).isoformat(),
            "end": (now + dt.timedelta(days=1)).isoformat(),
        }, secure=True)
        self.assertEqual(response.status_code, 200)
        by_id = {item["id"]: item for item in response.json()}
        self.assertIn(f"EVENTO:{event.pk}", by_id)
        self.assertIn(f"TAREA:{task.pk}", by_id)
        self.assertNotIn(f"TAREA:{hidden.pk}", by_id)
        self.assertEqual(by_id[f"TAREA:{task.pk}"]["extendedProps"]["company_id"], self.team.pk)

    def test_task_drag_and_completion_require_edit_scope(self):
        now = timezone.now().replace(second=0, microsecond=0)
        task = Tarea.objects.create(titulo="Movible", creador=self.user, team=self.team)
        task.asignados.add(self.user)
        moved = now + dt.timedelta(days=1)
        response = self.client.patch(
            reverse("tareas:api_detail", args=[task.pk]),
            data=json.dumps({"start": moved.isoformat(), "end": None}),
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.inicio_programado, moved)
        response = self.client.post(reverse("tareas:action", args=[task.pk]), {"action": "complete"}, secure=True)
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.estado, "hecha")

    def test_overdue_cutover_flag_excludes_legacy_rows(self):
        past = timezone.now() - dt.timedelta(hours=1)
        event = Event.objects.create(
            title="Legacy", calendar=self.calendar, start=past, end=past,
            created_by=self.user, team=self.team,
            seguimiento_atrasos_desde=None,
        )
        self.assertFalse(event.is_overdue)
        event.seguimiento_atrasos_desde = timezone.now()
        self.assertTrue(event.is_overdue)
