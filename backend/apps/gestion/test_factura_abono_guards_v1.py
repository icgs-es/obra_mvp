
import inspect

from pathlib import Path

from django.test import (
    SimpleTestCase,
)

from apps.gestion import views


class FacturaAbonoGuardsV1Tests(
    SimpleTestCase,
):

    def test_active_recalc_blocks_empty_lines(
        self,
    ):

        source = inspect.getsource(
            views.factura_recalcular_desde_lineas
        )

        self.assertIn(
            "if not lineas:",
            source,
        )


    def test_active_recalc_preserves_documentary_line_signs(
        self,
    ):

        source = inspect.getsource(
            views.factura_recalcular_desde_lineas
        )

        self.assertIn("FACTURA_LINEAS_SIGNO_DOCUMENTAL_V1", source)
        self.assertNotIn("base = -abs(base)", source)
        self.assertNotIn("iva = -abs(iva)", source)
        self.assertNotIn("total = -abs(total)", source)


    def test_active_plan_allows_abono_with_service_validation(
        self,
    ):

        source = inspect.getsource(
            views.factura_plan_pagos
        )

        self.assertNotIn("FACTURA_PLAN_ABONO_BACKEND_GUARD_V1", source)
        self.assertIn("autorizar_plan_pago", source)


    def test_detail_template_guards_actions(
        self,
    ):

        path = (
            Path(__file__)
            .resolve()
            .parents[2]
            / "templates"
            / "gestion"
            / "factura_detail.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "FACTURA_EMPTY_RECALC_UI_GUARD_V1",
            source,
        )

        self.assertIn(
            "auditoria.num_lineas",
            source,
        )

        self.assertIn("Crear y autorizar devoluciones", source)
        self.assertIn("plan de devoluciones", source)
