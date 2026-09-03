
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.gestion.templatetags.gestion_money import (
    factura_linea_total_iva_display,
)


class FacturaLineaTotalIvaDisplayV2Tests(
    SimpleTestCase
):

    def test_stale_legacy_total_does_not_win(self):

        line = SimpleNamespace(
            importe_linea=Decimal("48.00"),

            raw_data={
                "iva_porcentaje": "21.00",

                "importe_iva_linea": (
                    "10.08"
                ),

                "total_linea_con_iva": (
                    "58.08"
                ),

                # Residuos antiguos.
                "importe_total_con_iva": (
                    "-24.20"
                ),

                "total_con_iva": (
                    "-24.20"
                ),
            },
        )


        result = (
            factura_linea_total_iva_display(
                line
            )
        )


        self.assertEqual(
            result,
            "58,08 €",
        )


    def test_base_plus_exact_line_iva(self):

        line = SimpleNamespace(
            importe_linea=Decimal(
                "736.24"
            ),

            raw_data={
                "importe_iva_linea": (
                    "154.61"
                ),

                "total_linea_con_iva": (
                    "890.85"
                ),
            },
        )


        self.assertEqual(
            factura_linea_total_iva_display(
                line
            ),
            "890,85 €",
        )


    def test_negative_credit_is_still_valid(self):

        line = SimpleNamespace(
            importe_linea=Decimal(
                "-100.00"
            ),

            raw_data={
                "importe_iva_linea": (
                    "-21.00"
                ),
            },
        )


        self.assertEqual(
            factura_linea_total_iva_display(
                line
            ),
            "-121,00 €",
        )

