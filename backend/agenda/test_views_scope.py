import inspect
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from actividad.models import ActividadPlataforma
from usuarios.models import Team

from . import views
from .models import Calendar, Event


User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class AgendaEndpointScopeTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(
            name="Agenda Endpoint Team A"
        )

        self.team_b = Team.objects.create(
            name="Agenda Endpoint Team B"
        )

        self.user_a = User.objects.create_user(
            username="endpoint_user_a",
            password="x",
        )

        self.member_a = User.objects.create_user(
            username="endpoint_member_a",
            password="x",
        )

        self.manager_a = User.objects.create_user(
            username="endpoint_manager_a",
            password="x",
            is_staff=True,
        )

        self.user_b = User.objects.create_user(
            username="endpoint_user_b",
            password="x",
        )

        self.user_a.teams.add(self.team_a)
        self.member_a.teams.add(self.team_a)
        self.manager_a.teams.add(self.team_a)
        self.manager_a.groups.add(
            Group.objects.get_or_create(name="Gerencia")[0]
        )
        self.user_b.teams.add(self.team_b)

        self.private_a_calendar = (
            Calendar.objects.create(
                nombre="Privado A",
                tipo="PERSONAL",
                owner=self.user_a,
            )
        )

        self.global_calendar = (
            Calendar.objects.create(
                nombre="Global",
                tipo="ORG",
            )
        )

        self.start = (
            timezone.now()
            + timezone.timedelta(hours=2)
        )

        self.end = (
            self.start
            + timezone.timedelta(hours=1)
        )

        self.private_a = (
            Event.objects.create(
                team=self.team_a,
                title="Privado A",
                calendar=(
                    self.private_a_calendar
                ),
                start=self.start,
                end=self.end,
                visibility="PRIVADA",
                created_by=self.user_a,
            )
        )

        self.global_a = (
            Event.objects.create(
                team=self.team_a,
                title="Global A",
                calendar=(
                    self.global_calendar
                ),
                start=self.start,
                end=self.end,
                visibility="GLOBAL",
                created_by=self.user_a,
            )
        )

        self.global_b = (
            Event.objects.create(
                team=self.team_b,
                title="Global B",
                calendar=(
                    self.global_calendar
                ),
                start=self.start,
                end=self.end,
                visibility="GLOBAL",
                created_by=self.user_b,
            )
        )

    def login(
        self,
        user,
        active_team_id,
    ):
        self.client.force_login(user)

        session = self.client.session

        session["active_team_id"] = str(
            active_team_id
        )

        session[
            "_gestion_default_todas_empresas_user_id"
        ] = str(user.pk)

        session.save()

    def event_form_payload(
        self,
        *,
        title,
        calendar,
        visibility,
    ):
        local_start = timezone.localtime(
            self.start
        )

        local_end = timezone.localtime(
            self.end
        )

        return {
            "title": title,
            "calendar": calendar.pk,
            "start": local_start.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "end": local_end.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "all_day": "",
            "rrule": "",
            "rrule_until": "",
            "who_text": "",
            "who_users": [],
            "description": "",
            "status": "PENDIENTE",
            "location": "",
            "visibility": visibility,
        }

    def test_api_get_does_not_cross_team(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("agenda:api_events"),
            {
                "start": (
                    self.start
                    - timezone.timedelta(
                        days=1
                    )
                ).isoformat(),
                "end": (
                    self.end
                    + timezone.timedelta(
                        days=1
                    )
                ).isoformat(),
                "calendar": "global",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        titles = {
            item["title"]
            for item in response.json()
        }

        self.assertIn(
            self.global_a.title,
            titles,
        )

        self.assertNotIn(
            self.global_b.title,
            titles,
        )

    def test_api_create_requires_explicit_team(
        self,
    ):
        self.login(
            self.user_a,
            "all",
        )

        response = self.client.post(
            reverse("agenda:api_events"),
            data=json.dumps({
                "title": "API sin empresa",
                "start": (
                    self.start.isoformat()
                ),
                "end": (
                    self.end.isoformat()
                ),
                "visibility": "global",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertFalse(
            Event.objects.filter(
                title="API sin empresa"
            ).exists()
        )

    def test_form_create_requires_explicit_team(
        self,
    ):
        self.login(
            self.user_a,
            "all",
        )

        response = self.client.post(
            reverse("agenda:create"),
            data=self.event_form_payload(
                title="Form sin empresa",
                calendar=(
                    self.private_a_calendar
                ),
                visibility="PRIVADA",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Selecciona una empresa "
                "concreta"
            ),
        )

        self.assertFalse(
            Event.objects.filter(
                title="Form sin empresa"
            ).exists()
        )

    def test_cross_team_update_returns_404(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse(
                "agenda:edit",
                args=[self.global_b.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_manager_edits_shared_same_team(
        self,
    ):
        self.login(
            self.manager_a,
            self.team_a.pk,
        )

        response = self.client.post(
            reverse(
                "agenda:edit",
                args=[self.global_a.pk],
            ),
            data=self.event_form_payload(
                title="Global A editado",
                calendar=(
                    self.global_calendar
                ),
                visibility="GLOBAL",
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.global_a.refresh_from_db()

        self.assertEqual(
            self.global_a.title,
            "Global A editado",
        )

        self.assertEqual(
            self.global_a.updated_by,
            self.manager_a,
        )

    def test_manager_cannot_edit_private(
        self,
    ):
        self.login(
            self.manager_a,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse(
                "agenda:edit",
                args=[self.private_a.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_patch_sets_updated_by(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        new_start = (
            self.start
            + timezone.timedelta(hours=3)
        )

        new_end = (
            new_start
            + timezone.timedelta(hours=1)
        )

        response = self.client.patch(
            reverse(
                "agenda:api_event_detail",
                args=[self.global_a.pk],
            ),
            data=json.dumps({
                "start": (
                    new_start.isoformat()
                ),
                "end": (
                    new_end.isoformat()
                ),
                "allDay": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.global_a.refresh_from_db()

        self.assertEqual(
            self.global_a.updated_by,
            self.user_a,
        )

        self.assertEqual(
            self.global_a.start,
            new_start,
        )

    def test_cross_team_delete_returns_404(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        response = self.client.delete(
            reverse(
                "agenda:api_event_detail",
                args=[self.global_b.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.assertTrue(
            Event.objects.filter(
                pk=self.global_b.pk
            ).exists()
        )

    def test_export_does_not_cross_team(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        response = self.client.get(
            reverse("agenda:export"),
            {
                "start": (
                    self.start.date()
                    - timezone.timedelta(
                        days=1
                    )
                ).isoformat(),
                "end": (
                    self.end.date()
                    + timezone.timedelta(
                        days=1
                    )
                ).isoformat(),
                "calendar": "global",
            },
        )

        content = response.content.decode(
            "utf-8"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            self.global_a.title,
            content,
        )

        self.assertNotIn(
            self.global_b.title,
            content,
        )

    def test_import_assigns_explicit_team(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        csv_content = (
            "title,start,end,visibility\n"
            f"Importado A,"
            f"{self.start.isoformat()},"
            f"{self.end.isoformat()},"
            "GLOBAL\n"
        )

        response = self.client.post(
            reverse("agenda:import"),
            {
                "file": SimpleUploadedFile(
                    "agenda.csv",
                    csv_content.encode(
                        "utf-8"
                    ),
                    content_type="text/csv",
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        event = Event.objects.get(
            title="Importado A"
        )

        self.assertEqual(
            event.team,
            self.team_a,
        )

        self.assertEqual(
            event.created_by,
            self.user_a,
        )

    def test_ics_does_not_cross_team(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        token = "agenda-scope-token"

        views.TOKENS[token] = (
            self.user_a.pk
        )

        try:
            response = self.client.get(
                reverse(
                    "agenda:ics_feed",
                    args=[token],
                )
            )

        finally:
            views.TOKENS.pop(
                token,
                None,
            )

        content = response.content.decode(
            "utf-8"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            self.global_a.title,
            content,
        )

        self.assertNotIn(
            self.global_b.title,
            content,
        )

    def test_api_source_does_not_dump_payload(
        self,
    ):
        source = inspect.getsource(
            views.api_events
        )

        self.assertNotIn(
            "print(",
            source,
        )

        self.assertNotIn(
            "payload=%s",
            source,
        )

        self.assertNotIn(
            "request.body!r",
            source,
        )

    def test_api_create_registers_activity(
        self,
    ):
        self.login(
            self.user_a,
            self.team_a.pk,
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "agenda:api_events"
                ),
                data=json.dumps({
                    "title": (
                        "Actividad API activa"
                    ),
                    "start": (
                        self.start.isoformat()
                    ),
                    "end": (
                        self.end.isoformat()
                    ),
                    "visibility": "global",
                }),
                content_type=(
                    "application/json"
                ),
            )

        self.assertEqual(
            response.status_code,
            201,
        )

        activity = (
            ActividadPlataforma.objects
            .get(
                modulo="agenda",
                accion="crear_evento",
            )
        )

        self.assertEqual(
            activity.actor,
            self.user_a,
        )

        self.assertEqual(
            activity.team,
            self.team_a,
        )

        self.assertEqual(
            activity.visibilidad,
            "OBJETO",
        )
