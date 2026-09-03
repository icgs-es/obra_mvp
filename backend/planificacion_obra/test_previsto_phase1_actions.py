from datetime import time
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from planificacion_obra.test_services_reubicacion import (
    RelocationServiceRegressionTests,
)


class PrevistoPhase1ActionTests(
    RelocationServiceRegressionTests
):
    test_execute_single_relocation_updates_real_and_creates_audit = None
    test_execute_relocation_rolls_back_if_audit_fails = None

    def setUp(self):
        super().setUp()

        seed_real = (
            self.make_relocatable_real()
        )

        self.source_task = (
            seed_real.tarea_obra
        )

        self.assertIsNotNone(
            self.source_task
        )

        self.assertIsNotNone(
            self.source_task.obra_id
        )

        self.assertIsNotNone(
            self.source_task.unidad_obra_id
        )

        self.assertIsNotNone(
            self.source_task.partida_id
        )

        self.target_task = (
            self.make_target_task(
                self.source_task
            )
        )

        self.assertIsNotNone(
            self.target_task
        )

        self.assertEqual(
            self.target_task.team_id,
            self.source_task.team_id,
        )

        self.assertEqual(
            self.target_task.obra_id,
            self.source_task.obra_id,
        )

        self.assertEqual(
            self.target_task.partida_id,
            self.source_task.partida_id,
        )

        self.team = (
            self.source_task.team
        )

        self.assertIsNotNone(
            self.resource
        )

        self.assertEqual(
            self.resource.team_id,
            self.team.pk,
        )

        self.user = (
            getattr(
                self,
                "actor",
                None,
            )
            or getattr(
                self,
                "user",
                None,
            )
        )

        self.assertIsNotNone(
            self.user
        )

        self.user.is_superuser = True
        self.user.is_staff = True

        self.user.save(
            update_fields=[
                "is_superuser",
                "is_staff",
            ]
        )

        self.client.force_login(
            self.user
        )

        session = self.client.session

        session[
            "active_team_id"
        ] = str(
            self.team.pk
        )

        session.save()

        self.previsto = (
            self._create_previsto()
        )

    def _required_defaults(
        self,
        model,
        values,
    ):
        values = dict(values)

        for field in model._meta.concrete_fields:
            if field.primary_key:
                continue

            if field.name in values:
                continue

            if (
                field.has_default()
                or field.null
                or getattr(field, "auto_now", False)
                or getattr(field, "auto_now_add", False)
            ):
                continue

            if field.is_relation:
                raise AssertionError(
                    "Relación obligatoria no cubierta: "
                    f"{field.name}"
                )

            internal = field.get_internal_type()

            if internal in {
                "CharField",
                "TextField",
                "EmailField",
                "SlugField",
            }:
                values[field.name] = ""

            elif internal in {
                "IntegerField",
                "BigIntegerField",
                "SmallIntegerField",
                "PositiveIntegerField",
                "PositiveSmallIntegerField",
            }:
                values[field.name] = 0

            elif internal in {
                "DecimalField",
                "FloatField",
            }:
                values[field.name] = Decimal("0")

            elif internal == "BooleanField":
                values[field.name] = False

            elif internal == "JSONField":
                values[field.name] = {}

            elif internal == "DateField":
                values[field.name] = (
                    timezone.localdate()
                )

            elif internal == "DateTimeField":
                values[field.name] = (
                    timezone.now()
                )

            elif internal == "TimeField":
                values[field.name] = time(0, 0)

            elif internal == "UUIDField":
                values[field.name] = uuid4()

            elif internal == "BinaryField":
                values[field.name] = b""

            else:
                raise AssertionError(
                    "Campo obligatorio no cubierto: "
                    f"{field.name} ({internal})"
                )

        return values

    def _create_previsto(self):
        Prev = apps.get_model(
            "planificacion_obra",
            "TareaRecursoPrevisto",
        )

        values = {
            "team": self.team,
            "tarea_obra": self.source_task,
            "unidad_obra": (
                self.source_task.unidad_obra
            ),
            "partida": self.source_task.partida,
            "recurso": self.resource,
            "legacy_id_recurso": (
                self.resource.legacy_id
            ),
            "legacy_cod_obra": (
                self.source_task.legacy_cod_obra
            ),
            "legacy_cod_fase": (
                self.source_task.legacy_cod_fase
            ),
            "legacy_cod_vivienda": (
                self.source_task
                .legacy_cod_vivienda
                or ""
            ),
            "legacy_planta": (
                self.source_task.legacy_planta
                or ""
            ),
            "legacy_cod_partida": (
                self.source_task.legacy_partida
                or ""
            ),
            "unidad": (
                self.resource.unidad
                or "UD"
            ),
            "cantidad": Decimal("2"),
            "precio_unidad": Decimal("3"),
            "costo_recurso": Decimal("6"),
            "raw_data": {
                "legacy_marker": "KEEP",
            },
        }

        values = self._required_defaults(
            Prev,
            values,
        )

        return Prev.objects.create(**values)

    def _edit_payload(self):
        return {
            "recurso": self.resource.pk,
            "unidad": (
                self.resource.unidad
                or "UD"
            ),
            "cantidad": "5",
            "precio_unidad": "4",
            "costo_recurso": "20",
            "fecha_estimada_entrega": "",
        }

    def test_all_actions_are_visible_for_legacy_row(
        self,
    ):
        response = self.client.get(
            reverse(
                "planificacion_obra:"
                "planning_tarea_detail",
                args=[self.source_task.pk],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for name in (
            "tarea_recurso_previsto_update",
            "tarea_recurso_previsto_reubicar",
            "tarea_recurso_previsto_delete",
        ):
            url = reverse(
                "planificacion_obra:" + name,
                args=[self.previsto.pk],
            )

            self.assertContains(
                response,
                url,
            )

    def test_edit_preserves_legacy_origin_and_registers_activity(
        self,
    ):
        Activity = apps.get_model(
            "actividad",
            "ActividadPlataforma",
        )

        Audit = apps.get_model(
            "gestion",
            "GestionAuditLog",
        )

        activity_before = Activity.objects.count()
        audit_before = Audit.objects.count()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "planificacion_obra:"
                    "tarea_recurso_previsto_update",
                    args=[self.previsto.pk],
                ),
                data=self._edit_payload(),
                secure=True,
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.previsto.refresh_from_db()

        self.assertEqual(
            self.previsto.cantidad,
            Decimal("5"),
        )

        self.assertEqual(
            self.previsto.precio_unidad,
            Decimal("4"),
        )

        self.assertEqual(
            self.previsto.costo_recurso,
            Decimal("20"),
        )

        self.assertEqual(
            self.previsto.raw_data[
                "legacy_marker"
            ],
            "KEEP",
        )

        self.assertNotIn(
            "origen",
            self.previsto.raw_data,
        )

        self.assertEqual(
            Audit.objects.count(),
            audit_before + 1,
        )

        self.assertEqual(
            Activity.objects.count(),
            activity_before + 1,
        )

        self.assertTrue(
            Audit.objects.filter(
                accion=(
                    "EDITAR_RECURSO_PREVISTO"
                ),
                objeto_id=self.previsto.pk,
            ).exists()
        )

        self.assertTrue(
            Activity.objects.filter(
                accion=(
                    "editar_recurso_previsto"
                ),
                objeto_id=self.previsto.pk,
            ).exists()
        )

    def test_relocation_preserves_origin_and_registers_activity(
        self,
    ):
        Activity = apps.get_model(
            "actividad",
            "ActividadPlataforma",
        )

        Audit = apps.get_model(
            "gestion",
            "GestionAuditLog",
        )

        activity_before = Activity.objects.count()
        audit_before = Audit.objects.count()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "planificacion_obra:"
                    "tarea_recurso_previsto_reubicar",
                    args=[self.previsto.pk],
                ),
                data={
                    "target_task": (
                        self.target_task.pk
                    ),
                    "reason": (
                        "Corrección de vivienda "
                        "prevista"
                    ),
                },
                secure=True,
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.previsto.refresh_from_db()

        self.assertEqual(
            self.previsto.tarea_obra_id,
            self.target_task.pk,
        )

        self.assertEqual(
            self.previsto.unidad_obra_id,
            self.target_task.unidad_obra_id,
        )

        self.assertNotIn(
            "origen",
            self.previsto.raw_data,
        )

        self.assertEqual(
            Audit.objects.count(),
            audit_before + 1,
        )

        self.assertEqual(
            Activity.objects.count(),
            activity_before + 1,
        )

        self.assertTrue(
            Audit.objects.filter(
                accion=(
                    "REUBICAR_RECURSO_PREVISTO"
                ),
                objeto_id=self.previsto.pk,
            ).exists()
        )

        self.assertTrue(
            Activity.objects.filter(
                accion=(
                    "reubicar_recurso_previsto"
                ),
                objeto_id=self.previsto.pk,
            ).exists()
        )

    def test_delete_registers_audit_and_activity(
        self,
    ):
        Prev = apps.get_model(
            "planificacion_obra",
            "TareaRecursoPrevisto",
        )

        Activity = apps.get_model(
            "actividad",
            "ActividadPlataforma",
        )

        Audit = apps.get_model(
            "gestion",
            "GestionAuditLog",
        )

        previsto_id = self.previsto.pk

        activity_before = Activity.objects.count()
        audit_before = Audit.objects.count()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "planificacion_obra:"
                    "tarea_recurso_previsto_delete",
                    args=[previsto_id],
                ),
                secure=True,
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            Prev.objects.filter(
                pk=previsto_id
            ).exists()
        )

        self.assertEqual(
            Audit.objects.count(),
            audit_before + 1,
        )

        self.assertEqual(
            Activity.objects.count(),
            activity_before + 1,
        )

        self.assertTrue(
            Audit.objects.filter(
                accion=(
                    "ELIMINAR_RECURSO_PREVISTO"
                ),
                objeto_id=previsto_id,
            ).exists()
        )

        self.assertTrue(
            Activity.objects.filter(
                accion=(
                    "eliminar_recurso_previsto"
                ),
                objeto_id=previsto_id,
            ).exists()
        )

    def test_edit_rolls_back_if_registration_fails(
        self,
    ):
        original_quantity = self.previsto.cantidad
        original_raw = dict(
            self.previsto.raw_data
        )

        with patch(
            "planificacion_obra."
            "services_recursos_previstos."
            "registrar_edicion_previsto",
            side_effect=RuntimeError(
                "forced activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        "planificacion_obra:"
                        "tarea_recurso_previsto_update",
                        args=[self.previsto.pk],
                    ),
                    data=self._edit_payload(),
                    secure=True,
                )

        self.previsto.refresh_from_db()

        self.assertEqual(
            self.previsto.cantidad,
            original_quantity,
        )

        self.assertEqual(
            self.previsto.raw_data,
            original_raw,
        )

    def test_relocation_rolls_back_if_audit_fails(
        self,
    ):
        original_task_id = (
            self.previsto.tarea_obra_id
        )

        original_raw = dict(
            self.previsto.raw_data
        )

        with patch(
            "planificacion_obra."
            "services_recursos_previstos."
            "_register",
            side_effect=RuntimeError(
                "forced audit failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    reverse(
                        "planificacion_obra:"
                        "tarea_recurso_previsto_reubicar",
                        args=[self.previsto.pk],
                    ),
                    data={
                        "target_task": (
                            self.target_task.pk
                        ),
                        "reason": (
                            "Corrección forzada "
                            "para rollback"
                        ),
                    },
                    secure=True,
                )

        self.previsto.refresh_from_db()

        self.assertEqual(
            self.previsto.tarea_obra_id,
            original_task_id,
        )

        self.assertEqual(
            self.previsto.raw_data,
            original_raw,
        )
