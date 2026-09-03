import datetime as dt
from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.test import TestCase

from actividad.models import (
    ActividadPlataforma,
)
from rrhh.models import Empleado
from usuarios.models import Team

from .activity import (
    registrar_cambio_asignacion,
    registrar_creacion_asignacion,
    registrar_eliminacion_asignacion,
    registrar_realizacion_asignacion,
    registrar_repeticion_asignaciones,
    snapshot_asignacion,
)
from .models import (
    AsignacionObra,
    CapituloCatalogo,
    ObraPlanificacion,
    PartidaCatalogo,
    TareaObra,
    UnidadObra,
)


User = get_user_model()


class AssignmentActivityAdapterTests(
    TestCase
):
    def setUp(self):
        self.team = Team.objects.create(
            name=(
                "Assignment Activity Team"
            )
        )

        self.actor = (
            User.objects.create_user(
                username=(
                    "assignment_actor"
                ),
                password="x",
            )
        )

        self.affected_user = (
            User.objects.create_user(
                username=(
                    "assignment_affected"
                ),
                password="x",
            )
        )

        self.actor.teams.add(
            self.team
        )

        self.affected_user.teams.add(
            self.team
        )

        self.employee = (
            Empleado.objects.create(
                team=self.team,
                user=self.affected_user,
                codigo="EMP-ACT-1",
                nombre_completo=(
                    "Empleado Afectado"
                ),
                tipo_relacion="PROPIO",
                area_principal="OBRA",
                puesto="Oficial",
                profesion="Albañil",
                situacion="ACTIVO",
                es_fichable=True,
                es_planificable_obra=True,
                activo=True,
            )
        )

        self.second_employee = (
            Empleado.objects.create(
                team=self.team,
                codigo="EMP-ACT-2",
                nombre_completo=(
                    "Empleado Sin Usuario"
                ),
                tipo_relacion="PROPIO",
                area_principal="OBRA",
                puesto="Peón",
                profesion="Construcción",
                situacion="ACTIVO",
                es_fichable=True,
                es_planificable_obra=True,
                activo=True,
            )
        )

        self.obra = (
            ObraPlanificacion.objects.create(
                team=self.team,
                legacy_cod_obra=9001,
                codigo="OB-ACT",
                nombre=(
                    "Obra Actividad"
                ),
            )
        )

        self.capitulo = (
            CapituloCatalogo.objects.create(
                team=self.team,
                codigo="C01",
                nombre="Albañilería",
                orden=1,
            )
        )

        self.partida = (
            PartidaCatalogo.objects.create(
                team=self.team,
                capitulo=self.capitulo,
                codigo="01.001",
                nombre="Fábrica de ladrillo",
                tipo_partida="MATERIAL",
                unidad="M2",
            )
        )

        self.unidad = (
            UnidadObra.objects.create(
                team=self.team,
                obra=self.obra,
                legacy_cod_obra=9001,
                legacy_cod_fase=1,
                legacy_cod_vivienda="1",
                edificio="BLOQUE A",
                vivienda="1",
                nivel="PRINCIPAL",
                tipo="VIVIENDA",
            )
        )

        self.tarea = (
            TareaObra.objects.create(
                team=self.team,
                legacy_key=(
                    "ACTIVITY-ASSIGNMENT-1"
                ),
                obra=self.obra,
                unidad_obra=self.unidad,
                capitulo=self.capitulo,
                partida=self.partida,
                legacy_cod_obra=9001,
                legacy_cod_fase=1,
                legacy_cod_vivienda="1",
                legacy_planta="PRINCIPAL",
                legacy_capitulo="C01",
                legacy_partida="01.001",
                programacion="",
                tipo_partida="MATERIAL",
                unidad="M2",
            )
        )

        self.assignment = (
            AsignacionObra.objects.create(
                team=self.team,
                empleado=self.employee,
                tarea_obra=self.tarea,
                unidad_obra=self.unidad,
                capitulo=self.capitulo,
                partida=self.partida,
                fecha_inicio=dt.date(
                    2026,
                    7,
                    22,
                ),
                hora_inicio=dt.time(
                    8,
                    0,
                ),
                fecha_fin=dt.date(
                    2026,
                    7,
                    22,
                ),
                hora_fin=dt.time(
                    16,
                    0,
                ),
                estado="PENDIENTE",
                observaciones="",
                creado_por=self.actor,
            )
        )

    def call_kwargs(
        self,
        recorder,
    ):
        self.assertEqual(
            recorder.call_count,
            1,
        )

        return (
            recorder
            .call_args
            .kwargs
        )

    def test_snapshot_contains_affected_user(
        self,
    ):
        snapshot = snapshot_asignacion(
            self.assignment
        )

        self.assertEqual(
            snapshot[
                "empleado_id"
            ],
            self.employee.pk,
        )

        self.assertEqual(
            snapshot[
                "rrhh_empleado_id"
            ],
            self.employee.pk,
        )

        self.assertEqual(
            snapshot[
                "usuario_afectado_id"
            ],
            self.affected_user.pk,
        )

        self.assertEqual(
            snapshot["obra_id"],
            self.obra.pk,
        )

    def test_snapshot_allows_employee_without_user(
        self,
    ):
        self.assignment.empleado = (
            self.second_employee
        )

        self.assignment.save(
            update_fields=[
                "empleado",
                "actualizado_en",
            ]
        )

        snapshot = snapshot_asignacion(
            self.assignment
        )

        self.assertIsNone(
            snapshot[
                "usuario_afectado_id"
            ]
        )

    def test_creation_activity_contract(
        self,
    ):
        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_creacion_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["modulo"],
            "planificacion_obra",
        )

        self.assertEqual(
            kwargs["accion"],
            "asignar_personal_obra",
        )

        self.assertEqual(
            kwargs["visibilidad"],
            "EQUIPO",
        )

        self.assertEqual(
            kwargs["actor"],
            self.actor,
        )

        self.assertEqual(
            kwargs["team"],
            self.team,
        )

        self.assertEqual(
            kwargs["metadata"][
                "usuario_afectado_id"
            ],
            self.affected_user.pk,
        )

        self.assertTrue(
            kwargs["metadata"][
                (
                    "suprimir_actividad_"
                    "recurso_real_derivado"
                )
            ]
        )

    def test_realized_state_has_precedence(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        self.assignment.estado = (
            "REALIZADO"
        )

        self.assignment.fecha_inicio = (
            dt.date(
                2026,
                7,
                23,
            )
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_cambio_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                recurso_real_ids=[
                    1001,
                ],
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "realizar_"
                "asignacion_personal"
            ),
        )

        self.assertIn(
            "estado",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

        self.assertIn(
            "fecha_inicio",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

        self.assertEqual(
            kwargs["metadata"][
                "recurso_real_ids"
            ],
            [1001],
        )

    def test_employee_change_activity(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        self.assignment.empleado = (
            self.second_employee
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_cambio_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            "reasignar_personal_obra",
        )

        self.assertEqual(
            kwargs["metadata"][
                "empleado_anterior_id"
            ],
            self.employee.pk,
        )

        self.assertEqual(
            kwargs["metadata"][
                "empleado_id"
            ],
            self.second_employee.pk,
        )

    def test_destination_precedes_date_change(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        second_partida = (
            PartidaCatalogo.objects.create(
                team=self.team,
                capitulo=self.capitulo,
                codigo="01.002",
                nombre="Enfoscado",
                tipo_partida="MATERIAL",
                unidad="M2",
            )
        )

        self.assignment.partida = (
            second_partida
        )

        self.assignment.fecha_inicio = (
            dt.date(
                2026,
                7,
                24,
            )
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_cambio_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "cambiar_destino_"
                "asignacion_personal"
            ),
        )

    def test_temporal_change_activity(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        self.assignment.hora_fin = (
            dt.time(
                18,
                0,
            )
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_cambio_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "reprogramar_"
                "asignacion_personal"
            ),
        )

    def test_generic_edit_activity(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        self.assignment.observaciones = (
            "Usar acceso norte"
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_cambio_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "editar_"
                "asignacion_personal"
            ),
        )

    def test_no_change_creates_no_activity(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            result = (
                registrar_cambio_asignacion(
                    asignacion=(
                        self.assignment
                    ),
                    actor=self.actor,
                    anterior=previous,
                    diferir_hasta_commit=False,
                )
            )

        self.assertIsNone(result)

        recorder.assert_not_called()

    def test_explicit_realization_metadata(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        self.assignment.estado = (
            "REALIZADO"
        )

        self.assignment.save()

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_realizacion_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                recurso_real_ids=[
                    2001,
                    2002,
                ],
                recurso_real_creados=1,
                recurso_real_actualizados=1,
                operation_id=(
                    "realization-test"
                ),
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "realizar_"
                "asignacion_personal"
            ),
        )

        self.assertEqual(
            kwargs["metadata"][
                "recurso_real_ids"
            ],
            [
                2001,
                2002,
            ],
        )

        self.assertEqual(
            kwargs["metadata"][
                "recurso_real_creados"
            ],
            1,
        )

        self.assertEqual(
            kwargs["metadata"][
                "recurso_real_actualizados"
            ],
            1,
        )

    def test_delete_uses_previous_snapshot(
        self,
    ):
        previous = snapshot_asignacion(
            self.assignment
        )

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_eliminacion_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
                anterior=previous,
                recurso_real_eliminados_ids=[
                    3001,
                ],
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "eliminar_"
                "asignacion_personal"
            ),
        )

        self.assertEqual(
            kwargs["objeto_id"],
            self.assignment.pk,
        )

        self.assertEqual(
            kwargs["metadata"][
                (
                    "recurso_real_"
                    "eliminados_ids"
                )
            ],
            [3001],
        )

    def test_repeat_is_one_summary_activity(
        self,
    ):
        second = (
            AsignacionObra.objects.create(
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
                creado_por=self.actor,
            )
        )

        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            registrar_repeticion_asignaciones(
                asignaciones=[
                    self.assignment,
                    second,
                ],
                actor=self.actor,
                asignacion_origen_id=(
                    self.assignment.pk
                ),
                operation_id=(
                    "repeat-test"
                ),
                diferir_hasta_commit=False,
            )

        kwargs = self.call_kwargs(
            recorder
        )

        self.assertEqual(
            kwargs["accion"],
            (
                "repetir_"
                "asignacion_personal"
            ),
        )

        self.assertEqual(
            kwargs["metadata"][
                "cantidad"
            ],
            2,
        )

        self.assertEqual(
            len(
                kwargs["metadata"][
                    "asignacion_ids"
                ]
            ),
            2,
        )

        self.assertEqual(
            kwargs["clave_idempotencia"],
            (
                "planificacion_obra:"
                "asignaciones:repetir:"
                "repeat-test"
            ),
        )

    def test_empty_repeat_creates_no_activity(
        self,
    ):
        with patch(
            (
                "planificacion_obra."
                "activity."
                "registrar_actividad"
            )
        ) as recorder:
            result = (
                registrar_repeticion_asignaciones(
                    asignaciones=[],
                    actor=self.actor,
                    diferir_hasta_commit=False,
                )
            )

        self.assertIsNone(result)

        recorder.assert_not_called()

    def test_real_creation_idempotency(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            registrar_creacion_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
            )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            registrar_creacion_asignacion(
                asignacion=(
                    self.assignment
                ),
                actor=self.actor,
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
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.visibilidad,
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "usuario_afectado_id"
            ],
            self.affected_user.pk,
        )

    def test_direct_orm_create_has_no_signal(
        self,
    ):
        AsignacionObra.objects.create(
            team=self.team,
            empleado=self.second_employee,
            tarea_obra=self.tarea,
            unidad_obra=self.unidad,
            capitulo=self.capitulo,
            partida=self.partida,
            fecha_inicio=dt.date(
                2026,
                7,
                24,
            ),
            hora_inicio=dt.time(
                8,
                0,
            ),
            fecha_fin=dt.date(
                2026,
                7,
                24,
            ),
            hora_fin=dt.time(
                16,
                0,
            ),
            estado="PENDIENTE",
            creado_por=self.actor,
        )

        self.assertEqual(
            ActividadPlataforma.objects
            .count(),
            0,
        )
