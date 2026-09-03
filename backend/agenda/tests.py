from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Calendar, Event
from usuarios.models import Team

User = get_user_model()

@override_settings(SECURE_SSL_REDIRECT=False)
class AgendaFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="u1",
            password="x",
            email="u1@example.com",
        )

        self.team = Team.objects.create(
            name="Agenda Test Team",
        )

        self.user.teams.add(
            self.team
        )

        self.client.login(
            username="u1",
            password="x",
        )

        session = self.client.session
        session["active_team_id"] = str(
            self.team.pk
        )

        session[
            "_gestion_default_todas_empresas_user_id"
        ] = str(self.user.pk)

        session.save()

        self.cal = Calendar.objects.create(
            nombre="Cal",
            tipo="PERSONAL",
            owner=self.user,
        )

        self.global_cal = Calendar.objects.create(
            nombre="Global",
            tipo="ORG",
        )

    def test_create_event_form_and_list_api(self):
        start = timezone.now() + timezone.timedelta(hours=1)
        end = start + timezone.timedelta(hours=1)

        # Crear por formulario
        resp = self.client.post(reverse("agenda:create"), data={
            "title": "Cita",
            "calendar": self.cal.id,
            "start": start.strftime("%Y-%m-%dT%H:%M"),
            "end": end.strftime("%Y-%m-%dT%H:%M"),
            "all_day": "",
            "status": "PENDIENTE",
            "location": "Sala",
            "visibility": "PRIVADA",
        })
        self.assertEqual(resp.status_code, 302)
        ev = Event.objects.get(
            title="Cita"
        )

        self.assertEqual(
            ev.visibility,
            "PRIVADA",
        )

        self.assertEqual(
            ev.team,
            self.team,
        )

        # Debe salir en API events
        params = {
            "start": (start - timezone.timedelta(days=1)).isoformat(),
            "end": (end + timezone.timedelta(days=1)).isoformat(),
            "calendar": ["mis"],
        }
        resp = self.client.get(reverse("agenda:api_events"), params)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Cita", resp.content.decode())

    def test_api_create_event(self):
        start = (timezone.now() + timezone.timedelta(hours=2)).isoformat()
        payload = {
            "title": "API Cita",
            "start": start,
            "allDay": False,
            "visibility": "global",
            "location": "WEB",
        }
        resp = self.client.post(reverse("agenda:api_events"), data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        ev = Event.objects.get(
            title="API Cita"
        )

        self.assertEqual(
            ev.visibility,
            "GLOBAL",
        )

        self.assertEqual(
            ev.team,
            self.team,
        )

        self.assertEqual(
            ev.calendar,
            self.global_cal,
        )



    def test_api_without_active_calendar_returns_400(
        self,
    ):
        Calendar.objects.all().delete()

        start = (
            timezone.now()
            + timezone.timedelta(hours=2)
        ).isoformat()

        payload = {
            "title": "Sin calendario",
            "start": start,
            "allDay": False,
            "visibility": "global",
            "location": "WEB",
        }

        response = self.client.post(
            reverse("agenda:api_events"),
            data=payload,
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertFalse(
            Event.objects.filter(
                title="Sin calendario"
            ).exists()
        )
