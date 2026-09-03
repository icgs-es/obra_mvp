from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    extract_factura_lines_from_text,
)


SADEJO_TEXT = """
CARPINTERÍA METÁLICA SADEJO
Nº de la factura: 95
UND. MEDIDAS PRECIO TOTAL
1 2,00 x 2,30 0,00 €
0,00 €
1.434,31 €
1 1,28 x 0,57 0,00 €
220,00 €
2 1,10 x 0,45 110,00 €
0,00 €
0,00 €
Subtotal de
la factura: 1.764,31 €
Base
imponible: 1.764,31 €
IVA 21%: 370,51 €
TOTAL: 2.134,82 €
Fabricación y montaje de Mosquitera
DESCRIPCIÓN
Fabricación y montaje de ventana corredera de aluminio
Color RAL 916 SERIE Q95 con cristal 4/20/4 y persiana de
aluminio con motor y tapajuntas
Fabricación y montaje de puerta abatible de aluminio
Color Blanco
"""


class SadejoFacturaV1Tests(SimpleTestCase):
    def setUp(self):
        self.result = (
            extract_factura_lines_from_text(
                SADEJO_TEXT
            )
        )
        self.lines = self.result["lineas"]

    def test_detecta_tres_lineas(self):
        self.assertEqual(
            len(self.lines),
            3,
        )

    def test_importes_correctos(self):
        self.assertEqual(
            [
                item["importe_linea"]
                for item in self.lines
            ],
            [
                "1434.31",
                "220.00",
                "110.00",
            ],
        )

    def test_precio_mosquitera_derivado(self):
        self.assertEqual(
            self.lines[2]["cantidad"],
            "2.0000",
        )
        self.assertEqual(
            self.lines[2]["precio_unitario"],
            "55.0000",
        )

    def test_suma_y_totales(self):
        total = sum(
            Decimal(item["importe_linea"])
            for item in self.lines
        )

        self.assertEqual(
            total,
            Decimal("1764.31"),
        )
        self.assertEqual(
            self.result["iva"],
            "370.51",
        )
        self.assertEqual(
            self.result["total"],
            "2134.82",
        )

    def test_parser_especifico(self):
        self.assertEqual(
            self.result["parser"],
            "sadejo_factura_tabla_v1",
        )
