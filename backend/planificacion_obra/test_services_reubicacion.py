import copy
from unittest.mock import patch

from django.apps import apps

from planificacion_obra import (
    test_activity_recursos_reales
    as resource_adapter_tests
)
from planificacion_obra.services_reubicacion import (
    SCOPE_SINGLE,
    execute_relocation,
)


class RelocationServiceRegressionTests(
    resource_adapter_tests
    .ResourceRealActivityAdapterTests
):
    def setUp(self):
        super().setUp()

        self.Audit = apps.get_model(
            "gestion",
            "GestionAuditLog",
        )

        self.Activity = apps.get_model(
            "actividad",
            "ActividadPlataforma",
        )

        self.TareaObra = apps.get_model(
            "planificacion_obra",
            "TareaObra",
        )

        self.Recurso = apps.get_model(
            "planificacion_obra",
            "RecursoCatalogo",
        )

        self.resource = (
            self.Recurso.objects.create(
                team=self.team,
                legacy_id=990003,
                nombre=(
                    "Recurso prueba "
                    "reubicación"
                ),
                tipo="MATERIAL",
                unidad="UD",
                capitulo=self.capitulo,
                observaciones="",
                raw_data={
                    "origen_test": (
                        "test_services_"
                        "reubicacion"
                    ),
                },
            )
        )

    def make_relocatable_real(
        self,
    ):
        real = self.make_real()

        real.recurso = self.resource
        real.empleado = None
        real.legacy_id_recurso = (
            self.resource.legacy_id
        )
        real.legacy_tipo_recurso = (
            self.resource.tipo
            or ""
        )

        real.save(
            update_fields=[
                "recurso",
                "empleado",
                "legacy_id_recurso",
                "legacy_tipo_recurso",
            ]
        )

        real.refresh_from_db()

        self.assertEqual(
            real.recurso_id,
            self.resource.pk,
        )

        self.assertIsNone(
            real.empleado_id,
        )

        return real

    def make_target_task(
        self,
        source_task,
    ):
        self.assertIsNotNone(
            source_task,
        )

        self.assertIsNotNone(
            source_task.obra_id,
        )

        self.assertIsNotNone(
            source_task.unidad_obra_id,
        )

        self.assertIsNotNone(
            source_task.partida_id,
        )

        return self.TareaObra.objects.create(
            team=source_task.team,
            legacy_key=(
                "test-reubicacion:"
                f"{source_task.pk}:"
                f"{self._testMethodName}"
            ),
            obra=source_task.obra,
            unidad_obra=(
                source_task.unidad_obra
            ),
            capitulo=source_task.capitulo,
            partida=source_task.partida,
            legacy_cod_obra=(
                source_task.legacy_cod_obra
            ),
            legacy_cod_fase=990002,
            legacy_cod_vivienda=(
                "DESTINO-TEST"
            ),
            legacy_planta="DESTINO",
            legacy_capitulo=(
                source_task.legacy_capitulo
                or ""
            ),
            legacy_partida=(
                source_task.legacy_partida
                or ""
            ),
            programacion=(
                source_task.programacion
                or ""
            ),
            tipo_partida=(
                source_task.tipo_partida
                or ""
            ),
            unidad=(
                source_task.unidad
                or ""
            ),
            raw_data={
                "origen_test": (
                    "test_services_reubicacion"
                ),
            },
        )

    def relocation_audits(
        self,
        real,
    ):
        return self.Audit.objects.filter(
            accion="REUBICAR_IMPUTACION",
            entidad="TareaRecursoReal",
            objeto_id=real.pk,
        )

    def test_execute_single_relocation_updates_real_and_creates_audit(
        self,
    ):
        real = self.make_relocatable_real()

        self.assertIsNotNone(
            real.recurso_id,
        )

        source_task = real.tarea_obra

        target_task = self.make_target_task(
            source_task
        )

        activity_before = (
            self.Activity.objects.count()
        )

        audit_before = (
            self.relocation_audits(
                real
            ).count()
        )

        result = execute_relocation(
            real_id=real.pk,
            target_task_id=target_task.pk,
            scope=SCOPE_SINGLE,
            reason=(
                "Corrección controlada "
                "del destino de prueba."
            ),
            user=self.actor,
        )

        real.refresh_from_db()

        self.assertEqual(
            real.tarea_obra_id,
            target_task.pk,
        )

        self.assertEqual(
            real.unidad_obra_id,
            target_task.unidad_obra_id,
        )

        self.assertEqual(
            real.partida_id,
            target_task.partida_id,
        )

        self.assertEqual(
            real.legacy_cod_fase,
            target_task.legacy_cod_fase,
        )

        self.assertEqual(
            real.legacy_cod_vivienda,
            target_task.legacy_cod_vivienda,
        )

        self.assertEqual(
            real.legacy_planta,
            target_task.legacy_planta,
        )

        self.assertEqual(
            result["real_ids"],
            [real.pk],
        )

        self.assertEqual(
            result["count"],
            1,
        )

        self.assertEqual(
            result["source"]["task_id"],
            source_task.pk,
        )

        self.assertEqual(
            result["target"]["task_id"],
            target_task.pk,
        )

        operation_id = (
            result["operation_id"]
        )

        self.assertTrue(
            operation_id,
        )

        event = (
            real.raw_data[
                "ultima_reubicacion"
            ]
        )

        self.assertEqual(
            event["operation_id"],
            operation_id,
        )

        self.assertEqual(
            event["before"][
                "tarea_obra_id"
            ],
            source_task.pk,
        )

        self.assertEqual(
            event["after"][
                "tarea_obra_id"
            ],
            target_task.pk,
        )

        audits = (
            self.relocation_audits(
                real
            )
        )

        self.assertEqual(
            audits.count(),
            audit_before + 1,
        )

        audit = audits.latest(
            "pk"
        )

        self.assertEqual(
            audit.usuario_id,
            self.actor.pk,
        )

        self.assertEqual(
            audit.team_id,
            self.team.pk,
        )

        self.assertEqual(
            audit.metadata[
                "operation_id"
            ],
            operation_id,
        )

        self.assertEqual(
            audit.metadata[
                "real_ids"
            ],
            [real.pk],
        )

        self.assertEqual(
            audit.metadata[
                "source"
            ][
                "task_id"
            ],
            source_task.pk,
        )

        self.assertEqual(
            audit.metadata[
                "target"
            ][
                "task_id"
            ],
            target_task.pk,
        )

        self.assertEqual(
            self.Activity.objects.count(),
            activity_before,
        )

    def test_execute_relocation_rolls_back_if_audit_fails(
        self,
    ):
        real = self.make_relocatable_real()

        self.assertIsNotNone(
            real.recurso_id,
        )

        source_task = real.tarea_obra

        target_task = self.make_target_task(
            source_task
        )

        before = {
            "tarea_obra_id": (
                real.tarea_obra_id
            ),
            "unidad_obra_id": (
                real.unidad_obra_id
            ),
            "partida_id": (
                real.partida_id
            ),
            "legacy_cod_fase": (
                real.legacy_cod_fase
            ),
            "legacy_cod_vivienda": (
                real.legacy_cod_vivienda
            ),
            "legacy_planta": (
                real.legacy_planta
            ),
            "raw_data": copy.deepcopy(
                real.raw_data
            ),
        }

        audit_before = (
            self.relocation_audits(
                real
            ).count()
        )

        activity_before = (
            self.Activity.objects.count()
        )

        with patch.object(
            self.Audit.objects,
            "create",
            side_effect=RuntimeError(
                "audit failure test"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                execute_relocation(
                    real_id=real.pk,
                    target_task_id=(
                        target_task.pk
                    ),
                    scope=SCOPE_SINGLE,
                    reason=(
                        "Corrección controlada "
                        "con rollback de prueba."
                    ),
                    user=self.actor,
                )

        real.refresh_from_db()

        self.assertEqual(
            real.tarea_obra_id,
            before["tarea_obra_id"],
        )

        self.assertEqual(
            real.unidad_obra_id,
            before["unidad_obra_id"],
        )

        self.assertEqual(
            real.partida_id,
            before["partida_id"],
        )

        self.assertEqual(
            real.legacy_cod_fase,
            before["legacy_cod_fase"],
        )

        self.assertEqual(
            real.legacy_cod_vivienda,
            before[
                "legacy_cod_vivienda"
            ],
        )

        self.assertEqual(
            real.legacy_planta,
            before["legacy_planta"],
        )

        self.assertEqual(
            real.raw_data,
            before["raw_data"],
        )

        self.assertEqual(
            self.relocation_audits(
                real
            ).count(),
            audit_before,
        )

        self.assertEqual(
            self.Activity.objects.count(),
            activity_before,
        )


for _name in dir(
    resource_adapter_tests
    .ResourceRealActivityAdapterTests
):
    if _name.startswith("test_"):
        setattr(
            RelocationServiceRegressionTests,
            _name,
            None,
        )

del _name
