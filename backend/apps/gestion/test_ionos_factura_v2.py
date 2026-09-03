from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    extract_factura_lines_from_text,
)


IONOS_TEXT = """
IONOS Cloud S.L.U.
N.° de factura: 202786809655
Contrato: 91936430 - IONOS Hosting Plus
Con. Servicios facturados Tarifa Cantidad Importe (EUR) IVA
1 Cuota mensual 11.00 EUR al mes 1 m. 11,00 21,0 %
10.07.2026-09.08.2026
2 IONOS Correo Basic 5 2.50 EUR al mes 1 m. 2,50 21,0 %
12.06.2026-11.07.2026
3 IONOS Correo Profesional 1 Lic. 6.00 EUR al mes 1 m. 6,00 21,0 %
19.06.2026-18.07.2026
4 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
18.06.2026-17.07.2026
5 IONOS Site Scan & Repair 6.00 EUR al mes 1 m. 6,00 21,0 %
20.06.2026-19.07.2026
6 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
29.06.2026-28.07.2026
7 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
04.07.2026-03.08.2026
8 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
04.07.2026-03.08.2026
Con. Servicios facturados Tarifa Cantidad Importe (EUR) IVA
9 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
04.07.2026-03.08.2026
10 IONOS Escaner Antivirus
Premium
1.50 EUR al mes 1 m. 1,50 21,0 %
04.07.2026-03.08.2026
11 IONOS Site Scan & Repair 6.00 EUR al mes 1 m. 6,00 21,0 %
27.06.2026-26.07.2026
12 Descuento Descuento -3,00 21,0 %
Descuento en concepto 11
Válido de 27/02/2026 a 26/02/2027
13 IONOS Correo Profesional 1 Lic. 6.00 EUR al mes 1 m. 6,00 21,0 %
05.07.2026-04.08.2026
Total (base imponible) 43,50 EUR
+ IVA (21,0 %) 9,14 EUR
Total a pagar 52,64 EUR
"""


class IonosFacturaMultilineaV2Tests(
    SimpleTestCase
):
    def setUp(self):
        self.result = (
            extract_factura_lines_from_text(
                IONOS_TEXT
            )
        )
        self.lines = self.result["lineas"]

    def test_detecta_trece_lineas(self):
        self.assertEqual(
            len(self.lines),
            13,
        )

    def test_base_total_correcta(self):
        total = sum(
            Decimal(item["importe_linea"])
            for item in self.lines
        )

        self.assertEqual(
            total,
            Decimal("43.50"),
        )

        self.assertEqual(
            self.result["base_imponible"],
            "43.50",
        )

    def test_iva_y_total(self):
        self.assertEqual(
            self.result["iva"],
            "9.14",
        )

        self.assertEqual(
            self.result["total"],
            "52.64",
        )

    def test_multilineas_antivirus(self):
        antivirus = [
            item
            for item in self.lines
            if "Antivirus Premium"
            in item["descripcion"]
        ]

        self.assertEqual(
            len(antivirus),
            6,
        )

        self.assertTrue(
            all(
                item["importe_linea"]
                == "1.50"
                for item in antivirus
            )
        )

    def test_descuento_negativo(self):
        discount = self.lines[11]

        self.assertEqual(
            discount["linea"],
            12,
        )

        self.assertEqual(
            discount["importe_linea"],
            "-3.00",
        )

        self.assertEqual(
            discount["descuento"],
            "0.00",
        )

    def test_codigos_por_servicio(self):
        codes = {
            item["concepto"]: item["codigo"]
            for item in self.lines
        }

        self.assertGreaterEqual(
            len(codes),
            6,
        )

        self.assertTrue(
            all(
                code.startswith(
                    "IONOS-91936430-"
                )
                for code in codes.values()
            )
        )
