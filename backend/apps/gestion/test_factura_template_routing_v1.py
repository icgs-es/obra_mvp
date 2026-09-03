import inspect

from django.test import SimpleTestCase

from apps.gestion import views

from apps.gestion.services.facturas_pdf import (
    apply_factura_payload_by_template_v1,
)


class FacturaTemplateRoutingV1Tests(
    SimpleTestCase,
):

    OCR_JOMA = """
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


    def test_joma_selected_template_corrects_generic_payload(
        self,
    ):
        payload = {
            "text": self.OCR_JOMA,
            "numero_documento": "413",
            "fecha": "31/07/2026",
            "fecha_iso": "2026-07-31",
            "base_imponible": None,
            "iva": None,
            "total": "952.97",
        }

        result = apply_factura_payload_by_template_v1(
            payload,
            parser_key="joma_factura_valorada_v1",
        )

        self.assertEqual(
            result["numero_documento"],
            "020263519",
        )

        self.assertEqual(
            result["fecha_iso"],
            "2026-07-31",
        )

        self.assertEqual(
            result["base_imponible"],
            "342.00",
        )

        self.assertEqual(
            result["iva"],
            "71.82",
        )

        self.assertEqual(
            result["total"],
            "413.82",
        )

        self.assertEqual(
            len(result["lineas"]),
            3,
        )


    def test_unknown_template_preserves_payload(
        self,
    ):
        original = {
            "numero_documento": "X",
            "total": "10.00",
        }

        result = apply_factura_payload_by_template_v1(
            original.copy(),
            parser_key="unknown",
        )

        self.assertEqual(
            result,
            original,
        )


    def test_original_factura_view_has_two_routing_points(
        self,
    ):
        source = inspect.getsource(
            views._factura_desde_pdf_before_antidup_v1
        )

        self.assertEqual(
            source.count(
                "FACTURA_TEMPLATE_ROUTING_AFTER_SELECTION_V1"
            ),
            2,
        )

        # Cada bloque contiene:
        #   1 hasattr(...)
        #   1 llamada real
        #
        # Por tanto el nombre aparece 4 veces, pero solo
        # deben existir 2 invocaciones efectivas.
        self.assertEqual(
            source.count(
                "_facturas_pdf_template.apply_factura_payload_by_template_v1("
            ),
            2,
        )

        self.assertEqual(
            source.count(
                '"apply_factura_payload_by_template_v1"'
            ),
            2,
        )
