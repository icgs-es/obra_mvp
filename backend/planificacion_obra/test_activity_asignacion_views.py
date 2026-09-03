import datetime as dt
from types import SimpleNamespace
from unittest.mock import (
    Mock,
    patch,
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

from .models import AsignacionObra
from .test_activity_asignaciones import (
    AssignmentActivityAdapterTests,
)


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class AssignmentActivityViewTests(
    TestCase
):
    def setUp(self):
        AssignmentActivityAdapterTests.setUp(
            self
        )

        self.client.force_login(
            self.actor
        )

    def new_assignment(
        self,
        *,
        observations="",
    ):
        return AsignacionObra(
            team=self.team,
            empleado=self.employee,
            tarea_obra=self.tarea,
            unidad_obra=self.unidad,
            capitulo=self.capitulo,
            partida=self.partida,
            fecha_inicio=dt.date(
                2026,
                7,
                23,
            ),
            hora_inicio=dt.time(
                8,
                0,
            ),
            fecha_fin=dt.date(
                2026,
                7,
                23,
            ),
            hora_fin=dt.time(
                16,
                0,
            ),
            estado="PENDIENTE",
            observaciones=observations,
        )

    def valid_form(
        self,
        instance,
    ):
        form = Mock()

        form.is_valid.return_value = (
            True
        )

        form.save.return_value = (
            instance
        )

        return form

    def sync_pending(
        self,
        assignment,
        user=None,
    ):
        assignment.save()

        return (
            "pendiente",
            "Asignación guardada.",
        )

    def test_create_registers_single_activity(
        self,
    ):
        assignment = self.new_assignment(
            observations=(
                "CREATE VIEW TEST"
            ),
        )

        form = self.valid_form(
            assignment
        )

        with patch(
            (
                "planificacion_obra.views."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_create"
                        )
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            AsignacionObra.objects
            .filter(
                pk=assignment.pk
            )
            .exists()
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "asignar_personal_obra"
                ),
                objeto_id=assignment.pk,
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

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
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "estado_sync"
            ],
            "pendiente",
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [],
        )

        self.assertTrue(
            activity.metadata[
                (
                    "suprimir_actividad_"
                    "recurso_real_derivado"
                )
            ]
        )

    def test_repeat_registers_one_summary_activity(
        self,
    ):
        repeated = self.new_assignment(
            observations=(
                "REPEAT VIEW TEST"
            ),
        )

        form = self.valid_form(
            repeated
        )

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_repetir"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            AsignacionObra.objects
            .filter(
                pk=repeated.pk
            )
            .exists()
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "repetir_asignacion_personal"
                ),
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.objeto_id,
            self.assignment.pk,
        )

        self.assertEqual(
            activity.metadata[
                "asignacion_origen_id"
            ],
            self.assignment.pk,
        )

        self.assertEqual(
            activity.metadata[
                "asignacion_ids"
            ],
            [
                repeated.pk,
            ],
        )

        self.assertEqual(
            activity.metadata[
                "cantidad"
            ],
            1,
        )

        self.assertEqual(
            activity.metadata[
                "estado_sync"
            ],
            "pendiente",
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [],
        )

    def test_create_rolls_back_if_activity_fails(
        self,
    ):
        assignment = self.new_assignment(
            observations=(
                "CREATE ROLLBACK TEST"
            ),
        )

        form = self.valid_form(
            assignment
        )

        with patch(
            (
                "planificacion_obra.views."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_creacion_asignacion"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_create"
                        )
                    ),
                    {},
                )

        self.assertFalse(
            AsignacionObra.objects
            .filter(
                observaciones=(
                    "CREATE ROLLBACK TEST"
                )
            )
            .exists()
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_repeat_rolls_back_if_activity_fails(
        self,
    ):
        repeated = self.new_assignment(
            observations=(
                "REPEAT ROLLBACK TEST"
            ),
        )

        form = self.valid_form(
            repeated
        )

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_repeticion_"
                "asignaciones"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_repetir"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertFalse(
            AsignacionObra.objects
            .filter(
                observaciones=(
                    "REPEAT ROLLBACK TEST"
                )
            )
            .exists()
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_realize_registers_single_activity(
        self,
    ):
        yesterday = (
            timezone.localdate()
            - dt.timedelta(days=1)
        )

        self.assignment.fecha_inicio = (
            yesterday
        )
        self.assignment.fecha_fin = (
            yesterday
        )
        self.assignment.save(
            update_fields=[
                "fecha_inicio",
                "fecha_fin",
                "actualizado_en",
            ]
        )

        def realize(
            assignment,
            user=None,
        ):
            assignment.estado = (
                "REALIZADO"
            )
            assignment.save(
                update_fields=[
                    "estado",
                    "actualizado_en",
                ]
            )

            return SimpleNamespace(
                pk=9001,
                id=9001,
            )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [9001],
            ],
        ), patch(
            (
                "planificacion_obra."
                "services_realizacion."
                "realizar_asignacion_obra"
            ),
            side_effect=realize,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_realizar"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.estado,
            "REALIZADO",
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "realizar_"
                    "asignacion_personal"
                ),
                objeto_id=(
                    self.assignment.pk
                ),
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

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
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "estado_anterior"
            ],
            "PENDIENTE",
        )

        self.assertEqual(
            activity.metadata[
                "estado"
            ],
            "REALIZADO",
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [9001],
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_creados"
            ],
            1,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_actualizados"
            ],
            0,
        )

    def test_realize_existing_resource_is_updated(
        self,
    ):
        yesterday = (
            timezone.localdate()
            - dt.timedelta(days=1)
        )

        self.assignment.fecha_inicio = (
            yesterday
        )
        self.assignment.fecha_fin = (
            yesterday
        )
        self.assignment.save(
            update_fields=[
                "fecha_inicio",
                "fecha_fin",
                "actualizado_en",
            ]
        )

        def realize(
            assignment,
            user=None,
        ):
            assignment.estado = (
                "REALIZADO"
            )
            assignment.save(
                update_fields=[
                    "estado",
                    "actualizado_en",
                ]
            )

            return SimpleNamespace(
                pk=9001,
                id=9001,
            )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [9001],
                [9001],
            ],
        ), patch(
            (
                "planificacion_obra."
                "services_realizacion."
                "realizar_asignacion_obra"
            ),
            side_effect=realize,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_realizar"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        activity = (
            ActividadPlataforma.objects
            .get(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "realizar_"
                    "asignacion_personal"
                ),
            )
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [9001],
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_creados"
            ],
            0,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_actualizados"
            ],
            1,
        )

    def test_realize_rolls_back_if_activity_fails(
        self,
    ):
        yesterday = (
            timezone.localdate()
            - dt.timedelta(days=1)
        )

        self.assignment.fecha_inicio = (
            yesterday
        )
        self.assignment.fecha_fin = (
            yesterday
        )
        self.assignment.save(
            update_fields=[
                "fecha_inicio",
                "fecha_fin",
                "actualizado_en",
            ]
        )

        def realize(
            assignment,
            user=None,
        ):
            assignment.estado = (
                "REALIZADO"
            )
            assignment.save(
                update_fields=[
                    "estado",
                    "actualizado_en",
                ]
            )

            return SimpleNamespace(
                pk=9001,
                id=9001,
            )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [9001],
            ],
        ), patch(
            (
                "planificacion_obra."
                "services_realizacion."
                "realizar_asignacion_obra"
            ),
            side_effect=realize,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_realizacion_"
                "asignacion"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            response = self.client.post(
                reverse(
                    (
                        "planificacion_obra:"
                        "asignacion_realizar"
                    ),
                    args=[
                        self.assignment.pk
                    ],
                ),
                {},
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.estado,
            "PENDIENTE",
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_future_realize_creates_no_activity(
        self,
    ):
        tomorrow = (
            timezone.localdate()
            + dt.timedelta(days=1)
        )

        self.assignment.fecha_inicio = (
            tomorrow
        )
        self.assignment.fecha_fin = (
            tomorrow
        )
        self.assignment.save(
            update_fields=[
                "fecha_inicio",
                "fecha_fin",
                "actualizado_en",
            ]
        )

        with patch(
            (
                "planificacion_obra."
                "services_realizacion."
                "realizar_asignacion_obra"
            )
        ) as service, patch(
            (
                "planificacion_obra.views."
                "registrar_realizacion_"
                "asignacion"
            )
        ) as recorder:
            response = self.client.post(
                reverse(
                    (
                        "planificacion_obra:"
                        "asignacion_realizar"
                    ),
                    args=[
                        self.assignment.pk
                    ],
                ),
                {},
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        service.assert_not_called()
        recorder.assert_not_called()

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.estado,
            "PENDIENTE",
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_standard_update_registers_single_activity(
        self,
    ):
        original = (
            self.assignment.observaciones
        )

        def mutate(
            commit=False,
        ):
            self.assignment.observaciones = (
                "UPDATE VIEW TEST"
            )
            return self.assignment

        form = self.valid_form(
            self.assignment
        )
        form.save.side_effect = mutate

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [],
            ],
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_update"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                objeto_id=(
                    self.assignment.pk
                ),
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

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
            "EQUIPO",
        )
        self.assertEqual(
            activity.metadata[
                "fuente"
            ],
            "formulario",
        )
        self.assertEqual(
            activity.metadata[
                "recurso_real_anteriores_ids"
            ],
            [],
        )
        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [],
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.observaciones,
            "UPDATE VIEW TEST",
        )
        self.assertNotEqual(
            self.assignment.observaciones,
            original,
        )

    def test_standard_update_passes_resource_diff(
        self,
    ):
        def mutate(
            commit=False,
        ):
            self.assignment.observaciones = (
                "RESOURCE DIFF TEST"
            )
            return self.assignment

        form = self.valid_form(
            self.assignment
        )
        form.save.side_effect = mutate

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [7001],
                [7001, 7002],
            ],
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_cambio_asignacion"
            )
        ) as recorder:
            response = self.client.post(
                reverse(
                    (
                        "planificacion_obra:"
                        "asignacion_update"
                    ),
                    args=[
                        self.assignment.pk
                    ],
                ),
                {},
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        recorder.assert_called_once()

        kwargs = recorder.call_args.kwargs

        self.assertEqual(
            kwargs[
                "recurso_real_anteriores_ids"
            ],
            [7001],
        )
        self.assertEqual(
            kwargs["recurso_real_ids"],
            [7001, 7002],
        )
        self.assertEqual(
            kwargs["fuente"],
            "formulario",
        )

    def test_unchanged_standard_update_creates_no_activity(
        self,
    ):
        form = self.valid_form(
            self.assignment
        )

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [],
            ],
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_update"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_standard_update_rolls_back_if_activity_fails(
        self,
    ):
        original = (
            self.assignment.observaciones
        )

        def mutate(
            commit=False,
        ):
            self.assignment.observaciones = (
                "UPDATE ROLLBACK TEST"
            )
            return self.assignment

        form = self.valid_form(
            self.assignment
        )
        form.save.side_effect = mutate

        with patch(
            (
                "planificacion_obra.forms."
                "AsignacionObraForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_guardar_y_"
                "sincronizar_estado"
            ),
            side_effect=self.sync_pending,
        ), patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [],
            ],
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_cambio_asignacion"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_update"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {},
                )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.observaciones,
            original,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_adjust_before_realize_registers_activity(
        self,
    ):
        original_start = (
            self.assignment.fecha_inicio
        )
        original_end = (
            self.assignment.fecha_fin
        )

        new_date = (
            min(
                original_start,
                timezone.localdate(),
            )
            - dt.timedelta(days=2)
        )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [],
            ],
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_update"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {
                        "modo": (
                            "ajustar_realizado"
                        ),
                        "fecha_inicio": (
                            new_date.isoformat()
                        ),
                        "fecha_fin": (
                            new_date.isoformat()
                        ),
                        "hora_inicio": "08:00",
                        "hora_fin": "16:00",
                    },
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                objeto_id=(
                    self.assignment.pk
                ),
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

        self.assertEqual(
            activity.metadata[
                "fuente"
            ],
            "ajuste_previo_realizar",
        )
        self.assertEqual(
            activity.metadata[
                "recurso_real_anteriores_ids"
            ],
            [],
        )
        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [],
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.fecha_inicio,
            new_date,
        )
        self.assertEqual(
            self.assignment.fecha_fin,
            new_date,
        )
        self.assertNotEqual(
            self.assignment.fecha_inicio,
            original_start,
        )
        self.assertNotEqual(
            self.assignment.fecha_fin,
            original_end,
        )

    def test_adjust_before_realize_rolls_back_if_activity_fails(
        self,
    ):
        original_start = (
            self.assignment.fecha_inicio
        )
        original_end = (
            self.assignment.fecha_fin
        )
        original_start_time = (
            self.assignment.hora_inicio
        )
        original_end_time = (
            self.assignment.hora_fin
        )

        new_date = (
            min(
                original_start,
                timezone.localdate(),
            )
            - dt.timedelta(days=2)
        )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            side_effect=[
                [],
                [],
            ],
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_cambio_asignacion"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_update"
                        ),
                        args=[
                            self.assignment.pk
                        ],
                    ),
                    {
                        "modo": (
                            "ajustar_realizado"
                        ),
                        "fecha_inicio": (
                            new_date.isoformat()
                        ),
                        "fecha_fin": (
                            new_date.isoformat()
                        ),
                        "hora_inicio": "08:00",
                        "hora_fin": "16:00",
                    },
                )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.fecha_inicio,
            original_start,
        )
        self.assertEqual(
            self.assignment.fecha_fin,
            original_end,
        )
        self.assertEqual(
            self.assignment.hora_inicio,
            original_start_time,
        )
        self.assertEqual(
            self.assignment.hora_fin,
            original_end_time,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_delete_registers_single_activity(
        self,
    ):
        assignment_id = (
            self.assignment.pk
        )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            return_value=[
                7001,
                7002,
            ],
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_delete"
                        ),
                        args=[
                            assignment_id
                        ],
                    ),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            AsignacionObra.objects
            .filter(
                pk=assignment_id
            )
            .exists()
        )

        activities = (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "eliminar_"
                    "asignacion_personal"
                ),
                objeto_id=assignment_id,
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

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
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "asignacion_id"
            ],
            assignment_id,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_relacionados_ids"
            ],
            [
                7001,
                7002,
            ],
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_eliminados_ids"
            ],
            [],
        )

        self.assertTrue(
            activity.metadata[
                (
                    "suprimir_actividad_"
                    "recurso_real_derivado"
                )
            ]
        )

    def test_delete_rolls_back_if_activity_registration_fails(
        self,
    ):
        assignment_id = (
            self.assignment.pk
        )

        with patch(
            (
                "planificacion_obra.views."
                "_asignacion_recurso_real_"
                "portal_ids"
            ),
            return_value=[
                7001,
            ],
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_eliminacion_"
                "asignacion"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        (
                            "planificacion_obra:"
                            "asignacion_delete"
                        ),
                        args=[
                            assignment_id
                        ],
                    ),
                    {},
                )

        self.assertTrue(
            AsignacionObra.objects
            .filter(
                pk=assignment_id
            )
            .exists()
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )

    def test_delete_get_creates_no_activity(
        self,
    ):
        assignment_id = (
            self.assignment.pk
        )

        response = self.client.get(
            reverse(
                (
                    "planificacion_obra:"
                    "asignacion_delete"
                ),
                args=[
                    assignment_id
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            AsignacionObra.objects
            .filter(
                pk=assignment_id
            )
            .exists()
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
            .count(),
            0,
        )
