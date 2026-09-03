from decimal import Decimal

from django.test import (
    SimpleTestCase,
)

from apps.gestion.services.facturas_pdf import (
    _portal_joma_extract_header_v1,
    _portal_joma_extract_lines_v1,
)


class JomaFacturaValoradaV1Tests(
    SimpleTestCase,
):

    OCR = """
    --- PAGE 1 OCR ---
    Arroyo Granodilla, s/n - 29730 Rincón de la Victorio - Málaga
    Apdo. de correos n° 63
    Telátono 952.97.83.67 Máviles 607.32.53.80 - 696.89.34,55
    materialesjomasl hotmail.com

    OBRA GENERAL
    ADR MARTIN INVESTMENTS, Sa.

    O 20263519| 31/07/2026 1

    C/HEROES DE SOSTOA, 166 4° F
    29003 MALAGA
    B93578649

    - Albaran n° 0 202606888 - 06/07/2026

    8 0411004 CANTO RODADO 40/60 (BIG BAG) 2,00 115,0000 230,00
    1401009* PALET J 2,00 11,0000 22,00
    0707002 PORTE CAMION 1,00 90,0000 90,00

    TOTAL BRUTO Forma de Pago: TAL
    [34200 | pAGARESO DIAS FECHA FACTURA 413,82 Euro.

    Base Imponible Importe IVA
    342,00 21 71,82 Ptas.
    """


    def test_header_real_joma(
        self,
    ):
        h = (
            _portal_joma_extract_header_v1(
                self.OCR
            )
        )

        self.assertEqual(
            h[
                "num_factura_proveedor"
            ],
            "020263519",
        )

        self.assertEqual(
            h[
                "fecha_emision"
            ],
            "31/07/2026",
        )

        self.assertEqual(
            h[
                "importe_base_imponible"
            ],
            "342.00",
        )

        self.assertEqual(
            h[
                "importe_iva"
            ],
            "71.82",
        )

        self.assertEqual(
            h[
                "importe_factura"
            ],
            "413.82",
        )

        self.assertEqual(
            h[
                "iva_porcentaje"
            ],
            "21.00",
        )


    def test_detecta_tres_lineas(
        self,
    ):
        parsed = (
            _portal_joma_extract_lines_v1(
                self.OCR
            )
        )

        self.assertEqual(
            len(
                parsed["lineas"]
            ),
            3,
        )

        self.assertEqual(
            parsed[
                "total_lineas"
            ],
            "342.00",
        )

        self.assertEqual(
            parsed[
                "raw"
            ][
                "total_iva_lineas"
            ],
            "71.82",
        )


    def test_linea_canto_rodado(
        self,
    ):
        line = (
            _portal_joma_extract_lines_v1(
                self.OCR
            )[
                "lineas"
            ][0]
        )

        self.assertEqual(
            line["codigo"],
            "0411004",
        )

        self.assertEqual(
            line["cantidad"],
            "2.0000",
        )

        self.assertEqual(
            line["precio"],
            "115.0000",
        )

        self.assertEqual(
            line["importe"],
            "230.00",
        )


    def test_linea_palet(
        self,
    ):
        line = (
            _portal_joma_extract_lines_v1(
                self.OCR
            )[
                "lineas"
            ][1]
        )

        self.assertEqual(
            line["codigo"],
            "1401009*",
        )

        self.assertEqual(
            line["importe"],
            "22.00",
        )


    def test_linea_porte(
        self,
    ):
        line = (
            _portal_joma_extract_lines_v1(
                self.OCR
            )[
                "lineas"
            ][2]
        )

        self.assertEqual(
            line["codigo"],
            "0707002",
        )

        self.assertEqual(
            line["cantidad"],
            "1.0000",
        )

        self.assertEqual(
            line["precio"],
            "90.0000",
        )

        self.assertEqual(
            line["importe"],
            "90.00",
        )


    def test_totales_matematicos(
        self,
    ):
        parsed = (
            _portal_joma_extract_lines_v1(
                self.OCR
            )
        )

        base = sum(
            Decimal(
                x["importe"]
            )
            for x
            in parsed["lineas"]
        )

        iva = sum(
            Decimal(
                x[
                    "importe_iva_linea"
                ]
            )
            for x
            in parsed["lineas"]
        )

        self.assertEqual(
            base,
            Decimal("342.00"),
        )

        self.assertEqual(
            iva,
            Decimal("71.82"),
        )

        self.assertEqual(
            base + iva,
            Decimal("413.82"),
        )
