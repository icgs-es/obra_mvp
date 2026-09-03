import inspect

from django.test import SimpleTestCase

from apps.gestion import views

from apps.gestion.services.facturas_pdf import (
    extract_factura_lines_by_template_v1,
)


class FacturaLineasTemplateRoutingV1Tests(
    SimpleTestCase,
):

    JOMA_OCR = """
    --- PAGE 1 OCR ---

    Arroyo Granodilla, s/n
    Telátono 952.97.83.67

    ADR MARTIN INVESTMENTS, Sa.

    O 20263519| 31/07/2026 1

    - Albaran n° 0 202606888 - 06/07/2026

    8 0411004 CANTO RODADO 40/60 (BIG BAG) 2,00 115,0000 230,00
    1401009* PALET J 2,00 11,0000 22,00
    0707002 PORTE CAMION 1,00 90,0000 90,00

    TOTAL BRUTO Forma de Pago:
    [34200 | pAGARESO DIAS FECHA FACTURA 413,82 Euro.

    Base Imponible Importe IVA
    342,00 21 71,82 Ptas.
    """


    def test_joma_selected_template_detects_three_lines(
        self,
    ):
        parsed = (
            extract_factura_lines_by_template_v1(
                self.JOMA_OCR,
                parser_key=(
                    "joma_factura_valorada_v1"
                ),
            )
        )

        self.assertIsInstance(
            parsed,
            dict,
        )

        self.assertEqual(
            len(parsed["lineas"]),
            3,
        )

        self.assertEqual(
            parsed["total_lineas"],
            "342.00",
        )

        self.assertEqual(
            parsed["lineas"][0]["codigo"],
            "0411004",
        )

        self.assertEqual(
            parsed["lineas"][1]["codigo"],
            "1401009*",
        )

        self.assertEqual(
            parsed["lineas"][2]["codigo"],
            "0707002",
        )


    def test_view_uses_line_template_dispatcher(
        self,
    ):
        source = inspect.getsource(
            views.factura_lineas_desde_ocr
        )

        self.assertIn(
            "FACTURA_LINEAS_TEMPLATE_ROUTING_V1",
            source,
        )

        self.assertIn(
            "extract_factura_lines_by_template_v1",
            source,
        )


    def test_idaterm_contract_still_present(
        self,
    ):
        source = inspect.getsource(
            extract_factura_lines_by_template_v1
        )

        self.assertIn(
            "idaterm_factura_valorada_v1",
            source,
        )

        self.assertIn(
            "_portal_idaterm_factura_abono_extract_lines_v1",
            source,
        )
