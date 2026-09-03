
import copy
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from planificacion_obra.services_reubicacion import (
    SCOPE_SINGLE,
)
from planificacion_obra.test_services_reubicacion import (
    RelocationServiceRegressionTests,
)


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class RelocationActivityViewTests(
    RelocationServiceRegressionTests
):
    route_name = (
        "planificacion_obra:tarea_recurso_real_reubicar"
    )

    def setUp(self):
        super().setUp()

        self.client.force_login(
            self.actor
        )

        session = self.client.session
        session[
            "active_team_id"
        ] = str(self.team.pk)
        session.save()

    def make_view_real(
        self,
        *,
        manual=True,
        source=None,
    ):
        real = self.make_real(
            manual=manual,
            source=source,
        )

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

        return real

    def relocation_url(
        self,
        real,
    ):
        return reverse(
            self.route_name,
            args=[real.pk],
        )

    def relocation_payload(
        self,
        target,
    ):
        return {
            "target_task": str(
                target.pk
            ),
            "scope": SCOPE_SINGLE,
            "reason": (
                "Corrección manual del "
                "destino de imputación."
            ),
            "action": "confirm",
            "confirmation": "REUBICAR",
        }

    def activities(
        self,
    ):
        return self.Activity.objects.filter(
            modulo="planificacion_obra",
            accion=(
                "reubicar_recurso_real_manual"
            ),
        )

    def test_manual_relocation_registers_one_activity(
        self,
    ):
        real = self.make_view_real()
        source = real.tarea_obra
        target = self.make_target_task(
            source
        )

        activity_before = (
            self.activities().count()
        )

        audit_before = (
            self.relocation_audits(
                real
            ).count()
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                self.relocation_url(real),
                self.relocation_payload(
                    target
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        real.refresh_from_db()

        self.assertEqual(
            real.tarea_obra_id,
            target.pk,
        )

        self.assertEqual(
            self.activities().count(),
            activity_before + 1,
        )

        self.assertEqual(
            self.relocation_audits(
                real
            ).count(),
            audit_before + 1,
        )

        activity = (
            self.activities().latest(
                "pk"
            )
        )

        audit = (
            self.relocation_audits(
                real
            ).latest("pk")
        )

        operation_id = (
            audit.metadata[
                "operation_id"
            ]
        )

        self.assertEqual(
            activity.team_id,
            self.team.pk,
        )

        self.assertEqual(
            activity.actor_id,
            self.actor.pk,
        )

        self.assertEqual(
            activity.metadata[
                "operation_id"
            ],
            operation_id,
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            1,
        )

        self.assertEqual(
            activity.metadata[
                "origen_tarea_ids"
            ],
            [source.pk],
        )

        self.assertEqual(
            activity.metadata[
                "destino_tarea_ids"
            ],
            [target.pk],
        )

        self.assertEqual(
            activity.metadata[
                "resultado"
            ][
                "operation_id"
            ],
            operation_id,
        )

    def test_derived_relocation_creates_no_platform_activity(
        self,
    ):
        real = self.make_view_real(
            manual=False,
            source="management",
        )

        source = real.tarea_obra
        target = self.make_target_task(
            source
        )

        activity_before = (
            self.activities().count()
        )

        audit_before = (
            self.relocation_audits(
                real
            ).count()
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                self.relocation_url(real),
                self.relocation_payload(
                    target
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        real.refresh_from_db()

        self.assertEqual(
            real.tarea_obra_id,
            target.pk,
        )

        self.assertEqual(
            self.activities().count(),
            activity_before,
        )

        self.assertEqual(
            self.relocation_audits(
                real
            ).count(),
            audit_before + 1,
        )

    def test_activity_failure_rolls_back_relocation(
        self,
    ):
        real = self.make_view_real()
        source = real.tarea_obra
        target = self.make_target_task(
            source
        )

        raw_before = copy.deepcopy(
            real.raw_data
        )

        activity_before = (
            self.activities().count()
        )

        audit_before = (
            self.relocation_audits(
                real
            ).count()
        )

        with patch(
            (
                "planificacion_obra."
                "activity_recursos_reales."
                "registrar_reubicacion_"
                "recursos_reales_manuales"
            ),
            side_effect=RuntimeError(
                "activity failure test"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    self.relocation_url(
                        real
                    ),
                    self.relocation_payload(
                        target
                    ),
                )

        real.refresh_from_db()

        self.assertEqual(
            real.tarea_obra_id,
            source.pk,
        )

        self.assertEqual(
            real.raw_data,
            raw_before,
        )

        self.assertEqual(
            self.activities().count(),
            activity_before,
        )

        self.assertEqual(
            self.relocation_audits(
                real
            ).count(),
            audit_before,
        )


for _name in dir(
    RelocationServiceRegressionTests
):
    if _name.startswith("test_"):
        setattr(
            RelocationActivityViewTests,
            _name,
            None,
        )

del _name
