from django.test import SimpleTestCase

from apps.gestion.services.factura_router import (
    get_registered_parser_v1,
)


TEJEIRO_TEXT = r"""
TEJEIRO MATERIALES DE CONSTRUCCIÓN SL

INVERADRIDE GESTION, S.L.
CIF. B-02703833

N. FACTURA  325/26      Fecha de la factura:  28/08/2026

FECHA   CTAD   DESCRIPCIÓN   PRECIO UNID.   IMPORTE

OBRA EN CÓMPETA CARRIL CIRCUNVALACIÓN, 5

480 BLOQUES HORMIGON 40x20x20 0,85 408,00
1500 BLOQUES DE 23/10/8 0,17 255,00
300 RACILLONES DE 100/25/4 1,55 465,00
3 SACAS ARENA FINA 32,00 96,00
1 SACA ARENA 29,00 29,00
73 SACOS CEMENTO 25 KG. 4,10 299,30
30 SACOS ARLITA EXPANDIDA 8,10 243,00
3 DESCARGA GRUA 67,00 201,00
5 PALET MADERA PVGS. 18,00 90,00
2 PALET MADERA CMTO 18,00 36,00
4 PALET MADERA INDM. 18,00 72,00
1 PALET MADERA NORMAL 18,00 18,00
4 SACAS ARENA FINA 32,00 128,00
1 DESCARGA GRUA 67,00 67,00

Subtotal: 2.407,30 €
Tasa impositiva: 21% Impuestos: 505,53 €
A pagar: 2.912,83 €

En TEJEIRO MATERIALES DE CONSTRUCCION SL tratamos...
"""


class TejeiroFacturaParserTests(
    SimpleTestCase
):

    def setUp(self):
        self.spec = (
            get_registered_parser_v1(
                "tejeiro_factura_valorada_v1"
            )
        )

        self.assertIsNotNone(
            self.spec
        )

    def test_cabecera_real(self):
        header = self.spec[
            "header"
        ](TEJEIRO_TEXT)

        self.assertEqual(
            header[
                "num_factura_proveedor"
            ],
            "325/26",
        )

        self.assertEqual(
            header["fecha_iso"],
            "2026-08-28",
        )

        self.assertEqual(
            header["base_imponible"],
            "2407.30",
        )

        self.assertEqual(
            header["iva"],
            "505.53",
        )

        self.assertEqual(
            header["total"],
            "2912.83",
        )

        self.assertEqual(
            header["iva_porcentaje"],
            "21.00",
        )

        self.assertEqual(
            header["proveedor_detectado"],
            (
                "TEJEIRO MATERIALES "
                "DE CONSTRUCCION SL"
            ),
        )

    def test_detecta_14_lineas(self):
        result = self.spec[
            "lines"
        ](TEJEIRO_TEXT)

        self.assertEqual(
            len(result["lineas"]),
            14,
        )

        self.assertEqual(
            result["total_lineas"],
            "2407.30",
        )

        self.assertTrue(
            result[
                "line_sum_matches_base"
            ]
        )

        self.assertEqual(
            result["warnings"],
            [],
        )

    def test_primera_y_ultima_linea(self):
        result = self.spec[
            "lines"
        ](TEJEIRO_TEXT)

        first = result["lineas"][0]
        last = result["lineas"][-1]

        self.assertEqual(
            first["descripcion"],
            "BLOQUES HORMIGON 40x20x20",
        )

        self.assertEqual(
            first["cantidad"],
            "480.0000",
        )

        self.assertEqual(
            first["precio"],
            "0.8500",
        )

        self.assertEqual(
            first["importe"],
            "408.00",
        )

        self.assertEqual(
            last["descripcion"],
            "DESCARGA GRUA",
        )

        self.assertEqual(
            last["importe"],
            "67.00",
        )

    def test_codigo_sintetico_es_estable(self):
        result = self.spec[
            "lines"
        ](TEJEIRO_TEXT)

        arena = [
            row
            for row in result["lineas"]
            if row["descripcion"]
            == "SACAS ARENA FINA"
        ]

        self.assertEqual(
            len(arena),
            2,
        )

        self.assertEqual(
            arena[0][
                "codigo_detectado"
            ],
            arena[1][
                "codigo_detectado"
            ],
        )

        self.assertTrue(
            arena[0][
                "codigo_detectado"
            ].startswith("TEJ-")
        )
