import copy
import uuid
from decimal import Decimal

from django.db import transaction
from django.test import TestCase

from actividad.models import (
    ActividadPlataforma,
)

from .activity_recursos_reales import (
    es_recurso_real_manual,
    registrar_cambio_recurso_real_manual,
    registrar_creacion_recursos_reales_manuales,
    registrar_eliminacion_recurso_real_manual,
    registrar_reubicacion_recursos_reales_manuales,
    snapshot_recurso_real,
)
from .models import TareaRecursoReal
from .test_activity_asignaciones import (
    AssignmentActivityAdapterTests,
)


class ResourceRealActivityAdapterTests(
    TestCase
):
    def setUp(self):
        AssignmentActivityAdapterTests.setUp(
            self
        )

        self.sequence = 800000

    def make_real(
        self,
        *,
        manual=True,
        source=None,
        quantity="2.0000",
    ):
        self.sequence += 1

        raw_data = {}

        if manual:
            raw_data.update({
                "origen": "portal_manual",
                "creado_desde": (
                    "tarea_recurso_real_create"
                ),
                "created_by_user_id": (
                    self.actor.pk
                ),
            })

        if source:
            raw_data["source"] = source

        return TareaRecursoReal.objects.create(
            team=self.team,
            legacy_id_recurso_tarea=(
                self.sequence
            ),
            tarea_obra=self.tarea,
            unidad_obra=self.unidad,
            partida=self.partida,
            legacy_cod_vivienda="",
            legacy_planta="",
            legacy_capitulo="",
            legacy_partida="",
            legacy_tipo_recurso="",
            unidad="UD",
            cantidad=Decimal(quantity),
            precio_unidad=Decimal(
                "3.0000"
            ),
            costo_recurso=Decimal(
                "6.0000"
            ),
            costo_recurso_real=Decimal(
                "6.0000"
            ),
            id_proveedor="",
            cod_albaran="",
            cod_factura="",
            observaciones="",
            raw_data=raw_data,
        )

    def run_deferred(
        self,
        callback,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            return callback()

    def obra_activities(self):
        return (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                )
            )
        )

    def test_snapshot_contract(
        self,
    ):
        real = self.make_real()

        snapshot = snapshot_recurso_real(
            real
        )

        self.assertEqual(
            snapshot["id"],
            real.pk,
        )

        self.assertEqual(
            snapshot["team_id"],
            self.team.pk,
        )

        self.assertEqual(
            snapshot["cantidad"],
            "2.0000",
        )

        self.assertEqual(
            snapshot["origen"],
            "portal_manual",
        )

        self.assertEqual(
            snapshot["creado_desde"],
            (
                "tarea_recurso_real_create"
            ),
        )

        self.assertTrue(
            es_recurso_real_manual(
                snapshot
            )
        )

    def test_create_is_one_summary_activity(
        self,
    ):
        resources = [
            self.make_real(
                quantity="2.0000"
            ),
            self.make_real(
                quantity="3.0000"
            ),
            self.make_real(
                quantity="4.0000"
            ),
        ]

        operation_id = (
            uuid.uuid4().hex
        )

        self.run_deferred(
            lambda: (
                registrar_creacion_recursos_reales_manuales(
                    recursos_reales=resources,
                    actor=self.actor,
                    operation_id=operation_id,
                )
            )
        )

        activities = (
            self.obra_activities()
            .filter(
                accion=(
                    "crear_recurso_real_manual"
                )
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
            resources[0].pk,
        )

        self.assertEqual(
            activity.visibilidad,
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [
                item.pk
                for item in resources
            ],
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            3,
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_total"
            ],
            "9.0000",
        )

    def test_create_is_idempotent(
        self,
    ):
        real = self.make_real()
        operation_id = (
            uuid.uuid4().hex
        )

        for _ in range(2):
            self.run_deferred(
                lambda: (
                    registrar_creacion_recursos_reales_manuales(
                        recursos_reales=[
                            real,
                        ],
                        actor=self.actor,
                        operation_id=(
                            operation_id
                        ),
                    )
                )
            )

        self.assertEqual(
            self.obra_activities()
            .filter(
                accion=(
                    "crear_recurso_real_manual"
                )
            )
            .count(),
            1,
        )

    def test_assignment_derived_is_suppressed(
        self,
    ):
        real = self.make_real(
            manual=False,
            source=(
                "portal_asignacion_obra"
            ),
        )

        self.run_deferred(
            lambda: (
                registrar_creacion_recursos_reales_manuales(
                    recursos_reales=[
                        real,
                    ],
                    actor=self.actor,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )
            )
        )

        self.assertEqual(
            self.obra_activities().count(),
            0,
        )

    def test_management_derived_is_suppressed(
        self,
    ):
        real = self.make_real(
            manual=False,
            source=(
                "portal_gestion_"
                "lineas_compra_a_partida_v2"
            ),
        )

        self.run_deferred(
            lambda: (
                registrar_creacion_recursos_reales_manuales(
                    recursos_reales=[
                        real,
                    ],
                    actor=self.actor,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )
            )
        )

        self.assertEqual(
            self.obra_activities().count(),
            0,
        )

    def test_direct_orm_create_has_no_signal(
        self,
    ):
        self.make_real()

        self.assertEqual(
            self.obra_activities().count(),
            0,
        )

    def test_no_change_creates_no_activity(
        self,
    ):
        real = self.make_real()

        previous = snapshot_recurso_real(
            real
        )

        self.run_deferred(
            lambda: (
                registrar_cambio_recurso_real_manual(
                    recurso_real=real,
                    actor=self.actor,
                    anterior=previous,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )
            )
        )

        self.assertEqual(
            self.obra_activities().count(),
            0,
        )

    def test_quantity_change_activity(
        self,
    ):
        real = self.make_real()

        previous = snapshot_recurso_real(
            real
        )

        real.cantidad = Decimal(
            "8.0000"
        )

        real.costo_recurso_real = Decimal(
            "24.0000"
        )

        real.save(
            update_fields=[
                "cantidad",
                "costo_recurso_real",
                "updated_at",
            ]
        )

        self.run_deferred(
            lambda: (
                registrar_cambio_recurso_real_manual(
                    recurso_real=real,
                    actor=self.actor,
                    anterior=previous,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )
            )
        )

        activity = (
            self.obra_activities()
            .get(
                accion=(
                    "editar_recurso_real_manual"
                )
            )
        )

        self.assertEqual(
            activity.metadata[
                "categoria_cambio"
            ],
            "CANTIDAD_HORAS_COSTE",
        )

        self.assertIn(
            "cantidad",
            activity.metadata[
                "campos_cambiados"
            ],
        )

        self.assertIn(
            "costo_recurso_real",
            activity.metadata[
                "campos_cambiados"
            ],
        )

    def test_destination_has_precedence(
        self,
    ):
        real = self.make_real()

        previous = snapshot_recurso_real(
            real
        )

        current = copy.deepcopy(
            previous
        )

        current["tarea_obra_id"] = (
            999001
        )

        current["cantidad"] = (
            "12.0000"
        )

        self.run_deferred(
            lambda: (
                registrar_cambio_recurso_real_manual(
                    recurso_real=current,
                    actor=self.actor,
                    anterior=previous,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )
            )
        )

        activity = (
            self.obra_activities()
            .get(
                accion=(
                    "editar_recurso_real_manual"
                )
            )
        )

        self.assertEqual(
            activity.metadata[
                "categoria_cambio"
            ],
            "REUBICACION_DESTINO",
        )

    def test_delete_uses_previous_snapshot(
        self,
    ):
        real = self.make_real()

        previous = snapshot_recurso_real(
            real
        )

        real_id = real.pk

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            with transaction.atomic():
                registrar_eliminacion_recurso_real_manual(
                    recurso_real=real,
                    actor=self.actor,
                    anterior=previous,
                    operation_id=(
                        uuid.uuid4().hex
                    ),
                )

                real.delete()

        self.assertFalse(
            TareaRecursoReal.objects
            .filter(pk=real_id)
            .exists()
        )

        activity = (
            self.obra_activities()
            .get(
                accion=(
                    "eliminar_recurso_real_manual"
                )
            )
        )

        self.assertEqual(
            activity.objeto_id,
            real_id,
        )

        self.assertEqual(
            activity.metadata[
                "anterior"
            ]["id"],
            real_id,
        )

    def test_relocation_is_one_composite_activity(
        self,
    ):
        resources = [
            self.make_real(),
            self.make_real(),
        ]

        previous = [
            snapshot_recurso_real(item)
            for item in resources
        ]

        current = copy.deepcopy(
            previous
        )

        for item in current:
            item["tarea_obra_id"] = (
                999002
            )
            item["unidad_obra_id"] = (
                999003
            )

        operation_id = (
            uuid.uuid4().hex
        )

        self.run_deferred(
            lambda: (
                registrar_reubicacion_recursos_reales_manuales(
                    anteriores=resources,
                    posteriores=current,
                    actor=self.actor,
                    operation_id=(
                        operation_id
                    ),
                    reason=(
                        "Corrección del destino "
                        "de la imputación."
                    ),
                    result={
                        "count": 2,
                        "operation_id": (
                            operation_id
                        ),
                    },
                )
            )
        )

        activities = (
            self.obra_activities()
            .filter(
                accion=(
                    "reubicar_recurso_real_manual"
                )
            )
        )

        self.assertEqual(
            activities.count(),
            1,
        )

        activity = activities.get()

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            2,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            [
                item.pk
                for item in resources
            ],
        )

        self.assertEqual(
            activity.metadata[
                "destino_tarea_ids"
            ],
            [
                999002,
            ],
        )

        self.assertTrue(
            activity.metadata[
                "suprimir_actividad_por_fila"
            ]
        )
