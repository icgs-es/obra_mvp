from datetime import date

from django.test import SimpleTestCase

from apps.gestion.forms_pagos import (
    PlanPagoFormSet,
    RegistrarPagoVencimientoForm,
)


class FacturaPagosFechaIsoV1Tests(
    SimpleTestCase
):
    def test_fecha_vencimiento_inicial_se_renderiza_iso(
        self,
    ):
        formset = PlanPagoFormSet(
            initial=[
                {
                    "fecha_vencimiento": (
                        date(2026, 7, 27)
                    ),
                    "importe_previsto": "1432.64",
                    "forma_pago": "TRANSFERENCIA",
                }
            ],
            prefix="pagos",
        )

        html = str(
            formset.forms[0][
                "fecha_vencimiento"
            ]
        )

        self.assertIn(
            'value="2026-07-27"',
            html,
        )

    def test_fecha_real_pago_se_renderiza_iso(
        self,
    ):
        form = RegistrarPagoVencimientoForm(
            initial={
                "fecha_real_pago": (
                    date(2026, 7, 30)
                )
            }
        )

        html = str(
            form["fecha_real_pago"]
        )

        self.assertIn(
            'value="2026-07-30"',
            html,
        )
