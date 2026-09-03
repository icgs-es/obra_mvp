from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    _portal_joma_extract_header_v1,
    _portal_joma_extract_lines_v1,
)


class JomaFacturaGenericV2Tests(
    SimpleTestCase,
):

    POSITIVE = """
    JOMA MATERIALES

    O 20263519| 31/07/2026 1

    - Albaran n° 0 202606888 - 06/07/2026

    8 0411004 CANTO RODADO 40/60 (BIG BAG) 2,00 115,0000 230,00
    1401009* PALET J 2,00 11,0000 22,00
    0707002 PORTE CAMION 1,00 90,0000 90,00

    TOTAL BRUTO Forma de Pago:
    34200 PAGARE 60 DIAS FECHA FACTURA 413,82 Euro.

    Base Imponible Importe IVA
    342,00 21 71,82 Ptas.
    """


    NEGATIVE = """
    JOMA MATERIALES

    A 20260372| 31/07/2026 1

    - Albaran n° A 202600315 - 06/07/2026

    8 | 1401009* PALET J -1,00 10,0000 -10,00

    TOTAL BRUTO Forma de Pago:
    1000 PAGARE 60 DIAS FECHA FACTURA 712,10 Euro.

    Base Imponible Importe IVA Contravalor
    -10,00 21 -2,10 Ptas.
    """


    def test_positive_header(
        self,
    ):
        h = _portal_joma_extract_header_v1(
            self.POSITIVE
        )

        self.assertEqual(
            h["num_factura_proveedor"],
            "020263519",
        )

        self.assertEqual(
            h["importe_base_imponible"],
            "342.00",
        )

        self.assertEqual(
            h["importe_iva"],
            "71.82",
        )

        self.assertEqual(
            h["importe_factura"],
            "413.82",
        )

        self.assertFalse(
            h["total_reconciliado"]
        )


    def test_negative_header_and_bad_ocr_total(
        self,
    ):
        h = _portal_joma_extract_header_v1(
            self.NEGATIVE
        )

        self.assertEqual(
            h["num_factura_proveedor"],
            "A20260372",
        )

        self.assertEqual(
            h["fecha_emision"],
            "31/07/2026",
        )

        self.assertEqual(
            h["importe_base_imponible"],
            "-10.00",
        )

        self.assertEqual(
            h["importe_iva"],
            "-2.10",
        )

        self.assertEqual(
            h["total_documental_ocr"],
            "712.10",
        )

        self.assertEqual(
            h["importe_factura"],
            "-12.10",
        )

        self.assertTrue(
            h["total_reconciliado"]
        )


    def test_positive_three_lines(
        self,
    ):
        parsed = _portal_joma_extract_lines_v1(
            self.POSITIVE
        )

        self.assertEqual(
            len(parsed["lineas"]),
            3,
        )

        self.assertEqual(
            parsed["total_lineas"],
            "342.00",
        )


    def test_negative_one_line(
        self,
    ):
        parsed = _portal_joma_extract_lines_v1(
            self.NEGATIVE
        )

        self.assertEqual(
            len(parsed["lineas"]),
            1,
        )

        line = parsed["lineas"][0]

        self.assertEqual(
            line["codigo"],
            "1401009*",
        )

        self.assertEqual(
            line["cantidad"],
            "-1.0000",
        )

        self.assertEqual(
            line["precio"],
            "10.0000",
        )

        self.assertEqual(
            line["importe"],
            "-10.00",
        )

        self.assertEqual(
            parsed["total_lineas"],
            "-10.00",
        )


class JomaFacturaGenericV22RealOcrTests(
    SimpleTestCase,
):

    REAL_POSITIVE_LINES = """
    - Albaran n° 0 202606888 - 06/07/2026
      8 0411004 CANTO RODADO 40/60 (BIG BAG) 2,00 115,0000 230,00
      y
      E 1401009* PALET J 2,00 11,0000 22,00
      y
      3 0707002 PORTE CAMION 1,00 90,0000 90,00

    Base Imponible Importe IVA
    342,00 21 71,82 Ptas.
    """


    REAL_NEGATIVE_LINES = """
    - Albaran n° A 202600315 - 06/07/2026
      8 | 1401009* PALET J -1,00 10,0000 -10,00

    Base Imponible Importe IVA Contravalor
    -10,00 21 -2,10 Ptas.
    """


    def test_real_positive_ocr_noise_prefix(
        self,
    ):
        parsed = (
            _portal_joma_extract_lines_v1(
                self.REAL_POSITIVE_LINES
            )
        )

        codes = [
            item["codigo"]
            for item
            in parsed["lineas"]
        ]

        self.assertEqual(
            codes,
            [
                "0411004",
                "1401009*",
                "0707002",
            ],
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


    def test_real_negative_ocr_pipe_prefix(
        self,
    ):
        parsed = (
            _portal_joma_extract_lines_v1(
                self.REAL_NEGATIVE_LINES
            )
        )

        self.assertEqual(
            len(
                parsed["lineas"]
            ),
            1,
        )

        line = (
            parsed[
                "lineas"
            ][0]
        )

        self.assertEqual(
            line["codigo"],
            "1401009*",
        )

        self.assertEqual(
            line["cantidad"],
            "-1.0000",
        )

        self.assertEqual(
            line["importe"],
            "-10.00",
        )


    def test_albaran_number_is_never_article(
        self,
    ):
        parsed = (
            _portal_joma_extract_lines_v1(
                """
                - Albaran n° 0 202606888 - 06/07/2026
                - Albaran n° A 202600315 - 06/07/2026
                """
            )
        )

        self.assertEqual(
            parsed["lineas"],
            [],
        )
