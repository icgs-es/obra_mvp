from django.test import SimpleTestCase

from apps.gestion.services.factura_router import (
    _difalac_header_v1,
    _difalac_lines_v1,
    get_registered_parser_v1,
)


class DifalacFacturaValoradaV1Tests(SimpleTestCase):
    """Fixtures based on the real columnar DIFALAC PDF layout."""

    MULTIPAGE_LAYOUT = """
DISEÑO FABRICACION Y LACADO, S.L.
Número: A/9999
FECHA: 01/09/2026

ARTICULO       UDS                               DESCRIPCION                               Dto    IMPORTE           TOTAL
                 1    VIV 31
               2,5   BARANDILLA DE ACERO CON VIDRIO                                      12,00 €          30,00 €
                      TERMINACION SATINADA
                 1    CASA 126
                 1    PUERTA CON VIDRIO LAMINADO                                        120,00 €         120,00 €
--- PAGE 1 / 2 ---
DISEÑO FABRICACION Y LACADO, S.L.
                 1    VIV-45
              3,25   PASAMANOS METALICO                                                 10,00 €          32,50 €
                      CON ANCLAJES INCLUIDOS

         0% Descuento 5% de Retención                Suma Total          Base Imponible         21% de I.V.A.        Total factura
                      0,00 €        0,00 €             182,50 €             182,50 €            38,33 €         220,83 €
"""

    def test_real_layout_handles_multiline_decimal_and_page_break(self):
        parsed = _difalac_lines_v1(self.MULTIPAGE_LAYOUT)

        self.assertEqual(len(parsed["lineas"]), 3)
        self.assertEqual(parsed["total_lineas"], "182.50")
        self.assertEqual(parsed["expected_base"], "182.50")
        self.assertTrue(parsed["line_sum_matches_base"])
        self.assertEqual(parsed["lineas"][0]["cantidad"], "2.5000")
        self.assertEqual(parsed["lineas"][0]["precio"], "12.0000")
        self.assertIn("TERMINACION SATINADA", parsed["lineas"][0]["descripcion"])
        self.assertIn("CON ANCLAJES INCLUIDOS", parsed["lineas"][2]["descripcion"])

    def test_work_references_are_never_articles(self):
        parsed = _difalac_lines_v1(self.MULTIPAGE_LAYOUT)
        descriptions = "\n".join(line["descripcion"] for line in parsed["lineas"]).upper()

        self.assertNotIn("VIV 31", descriptions)
        self.assertNotIn("VIV-45", descriptions)
        self.assertNotIn("CASA 126", descriptions)

    def test_header_and_registry_are_format_driven(self):
        header = _difalac_header_v1(self.MULTIPAGE_LAYOUT)

        self.assertEqual(header["num_factura_proveedor"], "A/9999")
        self.assertEqual(header["fecha_iso"], "2026-09-01")
        self.assertEqual(header["base_imponible"], "182.50")
        self.assertEqual(header["iva"], "38.33")
        self.assertEqual(header["total"], "220.83")
        self.assertIsNotNone(get_registered_parser_v1("difalac_factura_valorada_v1"))
