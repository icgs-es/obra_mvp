import json

from django.contrib.auth import (
    get_user_model,
)
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone

from actividad.models import (
    ActividadPlataforma,
)
from usuarios.models import Team

from .models import (
    Calendar,
    Event,
)


User = get_user_model()


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class AgendaActivityViewTests(
    TestCase
):
    def setUp(self):
        self.team = Team.objects.create(
            name="Agenda Activity Views Team"
        )

        self.actor = (
            User.objects.create_user(
                username=(
                    "agenda_activity_view_actor"
                ),
                password="x",
            )
        )

        self.actor.teams.add(
            self.team
        )

        self.private_calendar = (
            Calendar.objects.create(
                nombre="Personal",
                tipo="PERSONAL",
                owner=self.actor,
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
            + timezone.timedelta(
                hours=2
            )
        )

        self.end = (
            self.start
            + timezone.timedelta(
                hours=1
            )
        )

        self.client.force_login(
            self.actor
        )

        session = self.client.session

        session[
            "active_team_id"
        ] = str(self.team.pk)

        session[
            "_gestion_default_todas_empresas_user_id"
        ] = str(self.actor.pk)

        session.save()

    def create_event(
        self,
        *,
        title="Evento existente",
        visibility="GLOBAL",
        status="PENDIENTE",
    ):
        calendar = (
            self.global_calendar
            if visibility == "GLOBAL"
            else self.private_calendar
        )

        return Event.objects.create(
            team=self.team,
            title=title,
            calendar=calendar,
            start=self.start,
            end=self.end,
            visibility=visibility,
            status=status,
            created_by=self.actor,
        )

    def form_payload(
        self,
        *,
        title,
        calendar,
        visibility,
        status="PENDIENTE",
        start=None,
        end=None,
        description="",
    ):
        start = timezone.localtime(
            start or self.start
        )

        end = timezone.localtime(
            end or self.end
        )

        return {
            "title": title,
            "calendar": calendar.pk,
            "start": start.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "end": end.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "all_day": "",
            "rrule": "",
            "rrule_until": "",
            "who_text": "",
            "who_users": [],
            "description": description,
            "status": status,
            "location": "",
            "visibility": visibility,
        }

    def get_single_activity(
        self,
        action,
    ):
        queryset = (
            ActividadPlataforma.objects
            .filter(
                modulo="agenda",
                accion=action,
            )
        )

        self.assertEqual(
            queryset.count(),
            1,
        )

        return queryset.get()

    def test_form_create_registers_private_activity(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse("agenda:create"),
                data=self.form_payload(
                    title="Evento privado creado",
                    calendar=(
                        self.private_calendar
                    ),
                    visibility="PRIVADA",
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        event = Event.objects.get(
            title="Evento privado creado"
        )

        activity = (
            self.get_single_activity(
                "crear_evento"
            )
        )

        self.assertEqual(
            activity.objeto_id,
            event.pk,
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.visibilidad,
            "ACTOR",
        )

    def test_completion_precedes_generic_edit(
        self,
    ):
        event = self.create_event()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "agenda:edit",
                    args=[event.pk],
                ),
                data=self.form_payload(
                    title="Evento completado",
                    calendar=(
                        self.global_calendar
                    ),
                    visibility="GLOBAL",
                    status="COMPLETADO",
                    description=(
                        "Descripción modificada"
                    ),
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        activity = (
            self.get_single_activity(
                "completar_evento"
            )
        )

        self.assertIn(
            "status",
            activity.metadata[
                "campos_cambiados"
            ],
        )

        self.assertIn(
            "description",
            activity.metadata[
                "campos_cambiados"
            ],
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(modulo="agenda")
            .count(),
            1,
        )

    def test_no_functional_change_creates_no_activity(
        self,
    ):
        event = self.create_event(
            title="Evento sin cambios"
        )

        event.start = event.start.replace(
            second=35,
            microsecond=336891,
        )

        event.end = event.end.replace(
            second=35,
            microsecond=336891,
        )

        event.save(
            update_fields=[
                "start",
                "end",
                "updated_at",
            ]
        )

        original_start = event.start
        original_end = event.end

        self.assertEqual(
            original_start.second,
            35,
        )

        self.assertEqual(
            original_start.microsecond,
            336891,
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "agenda:edit",
                    args=[event.pk],
                ),
                data=self.form_payload(
                    title=event.title,
                    calendar=(
                        self.global_calendar
                    ),
                    visibility="GLOBAL",
                    status=event.status,
                    description=(
                        event.description
                    ),
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        event.refresh_from_db()

        self.assertEqual(
            event.start,
            original_start,
        )

        self.assertEqual(
            event.end,
            original_end,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(modulo="agenda")
            .count(),
            0,
        )

    def test_patch_registers_reschedule(
        self,
    ):
        event = self.create_event()

        new_start = (
            self.start
            + timezone.timedelta(
                days=1
            )
        )

        new_end = (
            new_start
            + timezone.timedelta(
                hours=1
            )
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.patch(
                reverse(
                    "agenda:api_event_detail",
                    args=[event.pk],
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
                content_type=(
                    "application/json"
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        activity = (
            self.get_single_activity(
                "reprogramar_evento"
            )
        )

        self.assertEqual(
            activity.metadata[
                "inicio_anterior"
            ],
            self.start.isoformat(),
        )

        self.assertEqual(
            activity.metadata["inicio"],
            new_start.isoformat(),
        )

    def test_delete_registers_activity(
        self,
    ):
        event = self.create_event(
            title="Evento eliminado"
        )

        event_id = event.pk

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.delete(
                reverse(
                    "agenda:api_event_detail",
                    args=[event_id],
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            Event.objects.filter(
                pk=event_id
            ).exists()
        )

        activity = (
            self.get_single_activity(
                "eliminar_evento"
            )
        )

        self.assertEqual(
            activity.objeto_id,
            event_id,
        )

        self.assertEqual(
            activity.objeto_repr,
            "Evento eliminado",
        )

    def test_import_registers_one_summary_activity(
        self,
    ):
        second_start = (
            self.start
            + timezone.timedelta(
                hours=3
            )
        )

        second_end = (
            second_start
            + timezone.timedelta(
                hours=1
            )
        )

        csv_content = (
            "title,start,end,visibility\n"
            f"Importado uno,"
            f"{self.start.isoformat()},"
            f"{self.end.isoformat()},"
            "GLOBAL\n"
            f"Importado dos,"
            f"{second_start.isoformat()},"
            f"{second_end.isoformat()},"
            "GLOBAL\n"
        )

        uploaded = (
            SimpleUploadedFile(
                "agenda.csv",
                csv_content.encode(
                    "utf-8"
                ),
                content_type="text/csv",
            )
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse("agenda:import"),
                {
                    "file": uploaded,
                },
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            Event.objects.filter(
                title__startswith=(
                    "Importado "
                )
            ).count(),
            2,
        )

        activity = (
            self.get_single_activity(
                "importar_eventos"
            )
        )

        self.assertEqual(
            activity.metadata[
                "cantidad"
            ],
            2,
        )

        self.assertEqual(
            len(
                activity.metadata[
                    "evento_ids"
                ]
            ),
            2,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(modulo="agenda")
            .count(),
            1,
        )

    def test_api_create_registers_one_activity(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "agenda:api_events"
                ),
                data=json.dumps({
                    "title": (
                        "Evento API real"
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
            self.get_single_activity(
                "crear_evento"
            )
        )

        self.assertEqual(
            activity.visibilidad,
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "fuente"
            ],
            "api",
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(modulo="agenda")
            .count(),
            1,
        )
