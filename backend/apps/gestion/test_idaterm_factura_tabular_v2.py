
from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    _portal_idaterm_extract_factura_lines_tabular_v2,
)


class IdatermFacturaTabularGenericV2Tests(
    SimpleTestCase
):

    def test_material_y_porte(self):

        text = """
IDATERM, S.L.
CÓDIGO
DESCRIPCIÓN
CANTIDAD
PRECIO
DTO.
IMPORTE
Nº albarán AV26/29550 de fecha 29/07/26:
MEH82603000
CR2 ANGULO GALVANIZADO 23x34mm 3,00ml. -PLACO
Cód. productor-producto:
ENV/2023/000002888
540 PERFIL
1.620 ML
4,01
€/PERFIL
66
%
736,24
€
Hay 3 ML por PERFIL.
El precio por ML sale a 0,45€
1 CAMIÓN
PORTE CAMIÓN ZONA 1
1 PORTE
152
€/PORTE
0
%
152,00
€
"""

        p = (
            _portal_idaterm_extract_factura_lines_tabular_v2(
                text
            )
        )

        self.assertEqual(
            len(p["lineas"]),
            2,
        )

        a = p["lineas"][0]
        b = p["lineas"][1]

        self.assertEqual(
            a["codigo"],
            "MEH82603000",
        )

        self.assertIn(
            "CR2 ANGULO",
            a["descripcion"],
        )

        self.assertEqual(
            Decimal(a["cantidad"]),
            Decimal("540.0000"),
        )

        self.assertEqual(
            a["unidad"],
            "PERFIL",
        )

        self.assertEqual(
            Decimal(a["precio"]),
            Decimal("4.0100"),
        )

        self.assertEqual(
            Decimal(a["descuento"]),
            Decimal("66.00"),
        )

        self.assertEqual(
            Decimal(a["importe"]),
            Decimal("736.24"),
        )

        self.assertEqual(
            a["raw_data"][
                "cantidades_documento_secundarias"
            ][0]["cantidad"],
            "1620.0000",
        )

        self.assertEqual(
            a["raw_data"][
                "cantidades_documento_secundarias"
            ][0]["unidad"],
            "ML",
        )

        self.assertEqual(
            Decimal(b["cantidad"]),
            Decimal("1.0000"),
        )

        self.assertEqual(
            b["unidad"],
            "PORTE",
        )

        self.assertEqual(
            Decimal(b["precio"]),
            Decimal("152.0000"),
        )

        self.assertEqual(
            Decimal(b["descuento"]),
            Decimal("0.00"),
        )

        self.assertEqual(
            Decimal(b["importe"]),
            Decimal("152.00"),
        )

        self.assertEqual(
            Decimal(p["total_lineas"]),
            Decimal("888.24"),
        )


    def test_descuento_100_importe_cero(self):

        text = """
IDATERM, S.L.
610083
ACUSTIDAN 16/2 18mm. 6x1m. P/12. -DANOSA
8 ROLLO
111,60
€/ROLLO
51
%
437,47
€
1 CAMIÓN
PORTE CAMIÓN ZONA 1
1 PORTE
152
€/PORTE
100
%
0,00
€
"""

        p = (
            _portal_idaterm_extract_factura_lines_tabular_v2(
                text
            )
        )

        self.assertEqual(
            len(p["lineas"]),
            2,
        )

        self.assertEqual(
            Decimal(p["lineas"][0]["importe"]),
            Decimal("437.47"),
        )

        self.assertEqual(
            Decimal(p["lineas"][1]["descuento"]),
            Decimal("100.00"),
        )

        self.assertEqual(
            Decimal(p["lineas"][1]["importe"]),
            Decimal("0.00"),
        )

        self.assertEqual(
            Decimal(p["total_lineas"]),
            Decimal("437.47"),
        )


    def test_no_acepta_fila_que_no_cuadra(self):

        text = """
IDATERM, S.L.
ABC123
MATERIAL PRUEBA
10 UD
5,00
€/UD
0
%
999,00
€
"""

        p = (
            _portal_idaterm_extract_factura_lines_tabular_v2(
                text
            )
        )

        self.assertEqual(
            p["lineas"],
            [],
        )

        self.assertTrue(
            any(
                "ECONOMIC_MISMATCH"
                in x
                for x in p["debug"][
                    "discarded_lines"
                ]
            )
        )

