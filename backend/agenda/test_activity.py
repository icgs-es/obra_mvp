from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.test import TestCase
from django.utils import timezone

from actividad.models import (
    ActividadPlataforma,
)
from usuarios.models import Team

from .activity import (
    registrar_cambio_evento,
    registrar_creacion_evento,
    registrar_eliminacion_evento,
    registrar_importacion_eventos,
    snapshot_evento,
)
from .models import (
    Calendar,
    Event,
)


User = get_user_model()


class AgendaActivityAdapterTests(
    TestCase
):
    def setUp(self):
        self.team = Team.objects.create(
            name="Agenda Activity Team"
        )

        self.actor = (
            User.objects.create_user(
                username="agenda_actor",
                password="x",
            )
        )

        self.attendee = (
            User.objects.create_user(
                username="agenda_attendee",
                password="x",
            )
        )

        self.actor.teams.add(
            self.team
        )

        self.attendee.teams.add(
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
                hours=1
            )
        )

        self.end = (
            self.start
            + timezone.timedelta(
                hours=1
            )
        )

        self.event = Event.objects.create(
            team=self.team,
            title="Reunión de obra",
            calendar=(
                self.global_calendar
            ),
            start=self.start,
            end=self.end,
            visibility="GLOBAL",
            status="PENDIENTE",
            created_by=self.actor,
        )

    def recorder_call(
        self,
        recorder,
    ):
        self.assertEqual(
            recorder.call_count,
            1,
        )

        return recorder.call_args.kwargs

    def test_snapshot_contains_assignees(
        self,
    ):
        self.event.who_users.add(
            self.attendee
        )

        snapshot = snapshot_evento(
            self.event
        )

        self.assertEqual(
            snapshot["who_user_ids"],
            [self.attendee.pk],
        )

        self.assertEqual(
            snapshot["team_id"],
            self.team.pk,
        )

    def test_create_shared_event_activity(
        self,
    ):
        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_creacion_evento(
                evento=self.event,
                actor=self.actor,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "crear_evento",
        )

        self.assertEqual(
            kwargs["visibilidad"],
            "OBJETO",
        )

        self.assertEqual(
            kwargs["team"],
            self.team,
        )

        self.assertEqual(
            kwargs["clave_idempotencia"],
            (
                f"agenda:crear:"
                f"{self.event.pk}"
            ),
        )

    def test_private_event_activity_is_actor_only(
        self,
    ):
        private = Event.objects.create(
            team=self.team,
            title="Evento privado",
            calendar=(
                self.private_calendar
            ),
            start=self.start,
            end=self.end,
            visibility="PRIVADA",
            created_by=self.actor,
        )

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_creacion_evento(
                evento=private,
                actor=self.actor,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["visibilidad"],
            "OBJETO",
        )

    def test_completion_has_precedence(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        self.event.status = (
            Event.TaskStatus.COMPLETADO
        )

        self.event.start = (
            self.start
            + timezone.timedelta(
                days=1
            )
        )

        self.event.save()

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "completar_evento",
        )

        self.assertIn(
            "status",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

        self.assertIn(
            "start",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

    def test_reschedule_activity(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        self.event.start = (
            self.start
            + timezone.timedelta(
                hours=3
            )
        )

        self.event.save()

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "reprogramar_evento",
        )

    def test_attendee_change_activity(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        self.event.who_users.add(
            self.attendee
        )

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "cambiar_asistentes_evento"
            ),
        )

        self.assertEqual(
            kwargs["metadata"][
                "asistente_ids"
            ],
            [self.attendee.pk],
        )

    def test_state_change_activity(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        self.event.status = (
            Event.TaskStatus.EN_PROCESO
        )

        self.event.save()

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "cambiar_estado_evento",
        )

    def test_generic_edit_activity(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        self.event.description = (
            "Nueva descripción"
        )

        self.event.save()

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "editar_evento",
        )

    def test_no_change_creates_no_activity(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            result = registrar_cambio_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        self.assertIsNone(result)

        recorder.assert_not_called()

    def test_delete_activity_uses_snapshot(
        self,
    ):
        previous = snapshot_evento(
            self.event
        )

        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_eliminacion_evento(
                evento=self.event,
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "eliminar_evento",
        )

        self.assertEqual(
            kwargs["objeto_id"],
            self.event.pk,
        )

        self.assertEqual(
            kwargs["metadata"][
                "titulo"
            ],
            self.event.title,
        )

    def test_import_is_one_summary_activity(
        self,
    ):
        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            registrar_importacion_eventos(
                team=self.team,
                actor=self.actor,
                evento_ids=[
                    101,
                    102,
                    103,
                ],
                titulos=[
                    "Uno",
                    "Dos",
                    "Tres",
                ],
                omitidos=2,
                operation_id=(
                    "operation-test"
                ),
                diferir_hasta_commit=False,
            )

        kwargs = self.recorder_call(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "importar_eventos",
        )

        self.assertEqual(
            kwargs["metadata"][
                "cantidad"
            ],
            3,
        )

        self.assertEqual(
            kwargs["metadata"][
                "omitidos"
            ],
            2,
        )

        self.assertEqual(
            kwargs["clave_idempotencia"],
            (
                "agenda:importar:"
                "operation-test"
            ),
        )

    def test_empty_import_creates_no_activity(
        self,
    ):
        with patch(
            "agenda.activity.registrar_actividad"
        ) as recorder:
            result = (
                registrar_importacion_eventos(
                    team=self.team,
                    actor=self.actor,
                    evento_ids=[],
                    titulos=[],
                    diferir_hasta_commit=False,
                )
            )

        self.assertIsNone(result)

        recorder.assert_not_called()

    def test_real_activity_and_idempotency(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            registrar_creacion_evento(
                evento=self.event,
                actor=self.actor,
            )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            registrar_creacion_evento(
                evento=self.event,
                actor=self.actor,
            )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo="agenda",
                accion="crear_evento",
                objeto_id=self.event.pk,
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.visibilidad,
            "OBJETO",
        )

    def test_direct_orm_create_has_no_signal(
        self,
    ):
        Event.objects.create(
            team=self.team,
            title="Creación ORM directa",
            calendar=(
                self.global_calendar
            ),
            start=self.start,
            end=self.end,
            visibility="GLOBAL",
            created_by=self.actor,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            0,
        )
