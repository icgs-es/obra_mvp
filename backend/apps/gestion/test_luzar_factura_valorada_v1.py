from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    _portal_luzar_extract_header_v1,
    _portal_luzar_extract_lines_v1,
)


class LuzarFacturaValoradaV1Tests(
    SimpleTestCase,
):

    REAL_TEXT = """
    FACTURA
    Fecha
    Serie
    Canal
    Número
    Su Pedido
    Cliente31- 07- 2026
    359
    003126

    Obra:6-COMPETA

    Total EUR
    Albarán nº / 655 de fecha 28/07/2026 Su referencia:
    999032PUERTA THT SAGA100 CINTIA 1C/3P 900X2100
    RAL7016 C/ MIRILLA Y ACCESORIOS ESTANDAR
    INOX 320,000020,00 6.400,00
    039507PREMARCO PUERTA ENTRADA THT 1H 900X2100
    42,900020,00 858,00
    999032MANILLON INOX. MOD. BERLIN L1000MM
    PREMONTADO 55,000020,00 1.100,00
    036183** 9UD DCHA Y 11UD IZDA

    Dto. PP
    Importe neto
    Base IVA
    % IVA
    21,00
    8.358,008.358,00
    1.755,18

    Formas de pagoTransferencia 30 días
    Retención

    Vencimientos
    IMPORTE TOTAL30-08-202610.113,18 € 10.113,18
    """


    def test_header(
        self,
    ):

        h = (
            _portal_luzar_extract_header_v1(
                self.REAL_TEXT
            )
        )

        self.assertEqual(
            h["num_factura_proveedor"],
            "359",
        )

        self.assertEqual(
            h["fecha_emision"],
            "31/07/2026",
        )

        self.assertEqual(
            h["fecha_iso"],
            "2026-07-31",
        )

        self.assertEqual(
            h["importe_base_imponible"],
            "8358.00",
        )

        self.assertEqual(
            h["importe_iva"],
            "1755.18",
        )

        self.assertEqual(
            h["importe_factura"],
            "10113.18",
        )

        self.assertEqual(
            h["iva_porcentaje"],
            "21.00",
        )

        self.assertEqual(
            h["num_albaran_proveedor"],
            "655",
        )

        self.assertEqual(
            h["fecha_albaran"],
            "28/07/2026",
        )


    def test_four_lines(
        self,
    ):

        parsed = (
            _portal_luzar_extract_lines_v1(
                self.REAL_TEXT
            )
        )

        self.assertEqual(
            len(parsed["lineas"]),
            4,
        )

        codes = [
            x["codigo"]
            for x in parsed["lineas"]
        ]

        self.assertEqual(
            codes,
            [
                "999032",
                "039507",
                "999032",
                "036183",
            ],
        )


    def test_three_valued_lines(
        self,
    ):

        parsed = (
            _portal_luzar_extract_lines_v1(
                self.REAL_TEXT
            )
        )

        l1, l2, l3, _ = (
            parsed["lineas"]
        )

        self.assertEqual(
            l1["cantidad"],
            "20.0000",
        )

        self.assertEqual(
            l1["precio"],
            "320.0000",
        )

        self.assertEqual(
            l1["importe"],
            "6400.00",
        )

        self.assertEqual(
            l2["importe"],
            "858.00",
        )

        self.assertEqual(
            l3["importe"],
            "1100.00",
        )


    def test_non_valued_line_preserved(
        self,
    ):

        parsed = (
            _portal_luzar_extract_lines_v1(
                self.REAL_TEXT
            )
        )

        line = parsed["lineas"][3]

        self.assertEqual(
            line["codigo"],
            "036183",
        )

        self.assertTrue(
            line["es_no_valorada"]
        )

        self.assertEqual(
            line["importe"],
            "0.00",
        )


    def test_totals(
        self,
    ):

        parsed = (
            _portal_luzar_extract_lines_v1(
                self.REAL_TEXT
            )
        )

        self.assertEqual(
            parsed["total_lineas"],
            "8358.00",
        )

        self.assertEqual(
            parsed["raw"]["total_iva_lineas"],
            "1755.18",
        )


class LuzarFacturaCompactV12Tests(
    SimpleTestCase,
):

    def test_dimension_does_not_contaminate_price(
        self,
    ):
        from apps.gestion.services.facturas_pdf import (
            _portal_luzar_split_compact_values_v1_2,
        )


        solved = (
            _portal_luzar_split_compact_values_v1_2(
                (
                    "PREMARCO PUERTA ENTRADA THT "
                    "1H 900X210042,900020,00 858,00"
                )
            )
        )


        self.assertIsNotNone(
            solved
        )


        self.assertEqual(
            solved["description"],
            (
                "PREMARCO PUERTA ENTRADA THT "
                "1H 900X2100"
            ),
        )


        self.assertEqual(
            str(solved["cantidad"]),
            "20.00",
        )


        self.assertEqual(
            str(solved["precio"]),
            "42.9000",
        )


        self.assertEqual(
            str(solved["importe"]),
            "858.00",
        )


    def test_three_real_compact_tails(
        self,
    ):
        from apps.gestion.services.facturas_pdf import (
            _portal_luzar_split_compact_values_v1_2,
        )


        cases = [

            (
                (
                    "PUERTA THT SAGA100 CINTIA "
                    "INOX 320,000020,00 6.400,00"
                ),
                "20.00",
                "320.0000",
                "6400.00",
            ),

            (
                (
                    "PREMARCO PUERTA ENTRADA "
                    "1H 900X210042,900020,00 858,00"
                ),
                "20.00",
                "42.9000",
                "858.00",
            ),

            (
                (
                    "MANILLON INOX. MOD. BERLIN "
                    "PREMONTADO 55,000020,00 1.100,00"
                ),
                "20.00",
                "55.0000",
                "1100.00",
            ),
        ]


        for (
            raw,
            qty,
            price,
            amount,
        ) in cases:

            solved = (
                _portal_luzar_split_compact_values_v1_2(
                    raw
                )
            )

            self.assertIsNotNone(
                solved
            )

            self.assertEqual(
                str(solved["cantidad"]),
                qty,
            )

            self.assertEqual(
                str(solved["precio"]),
                price,
            )

            self.assertEqual(
                str(solved["importe"]),
                amount,
            )
