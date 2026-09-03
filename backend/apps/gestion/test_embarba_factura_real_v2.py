
from django.test import SimpleTestCase

from apps.gestion.services import (
    facturas_pdf,
)


REAL_LAYOUT_781 = """
B93578649R26  143.781 01/08/2026
FACTURA FECHA FACTURA
430030962
C O N C E P T OCANTIDAD IMPORTE
Página 1 de 1
POR EL SERVICIO DE MANTENIMIENTO EN EL/LOS ASCENSOR/ES
CORRESPONDIENTES AL MES DE AGOSTO
MANTENIMIENTO PREMIER  30,00
A partir del 1 de Julio de 2024
ExentoTotal Bruto
30,00 30,00 6,30 21,00
% IvaBases Iva Cuota Iva % Retenc. Retención
TOTAL FACTURA
36,30
"""


OLD_LAYOUT_782 = """
R26 143.782 01/08/2026
FACTURA FECHA FACTURA
430030962
CANTIDAD C O N C E P T O IMPORTE
MANTENIMIENTO PLATINUM 160,00
ARRENDAMIENTO MODULAR 5,60
SERVICIO DE COMUNICACION BIDIRECCIONAL 10,44
A partir del 1 de Julio de 2024
Total Bruto Exento
176,04 176,04 21,00 36,97
TOTAL FACTURA
213,01
"""


class EmbarbaFacturaRealV2R1Tests(
    SimpleTestCase,
):

    def test_real_781_header(
        self,
    ):

        h = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                REAL_LAYOUT_781
            )
        )


        self.assertEqual(
            h[
                "num_factura_proveedor"
            ],
            "R26 143.781",
        )

        self.assertEqual(
            h[
                "fecha_emision"
            ],
            "01/08/2026",
        )

        self.assertEqual(
            h[
                "importe_base_imponible"
            ],
            "30.00",
        )

        self.assertEqual(
            h[
                "importe_iva"
            ],
            "6.30",
        )

        self.assertEqual(
            h[
                "iva_porcentaje"
            ],
            "21.00",
        )

        self.assertEqual(
            h[
                "importe_factura"
            ],
            "36.30",
        )


    def test_real_781_line(
        self,
    ):

        p = (
            facturas_pdf
            ._portal_embarba_extract_lines_v1(
                REAL_LAYOUT_781
            )
        )


        self.assertEqual(
            len(
                p[
                    "lineas"
                ]
            ),
            1,
        )

        self.assertEqual(
            p[
                "lineas"
            ][0][
                "descripcion"
            ],
            "MANTENIMIENTO PREMIER",
        )

        self.assertEqual(
            p[
                "lineas"
            ][0][
                "cantidad"
            ],
            "1.0000",
        )

        self.assertEqual(
            p[
                "lineas"
            ][0][
                "precio_unitario"
            ],
            "30.0000",
        )

        self.assertEqual(
            p[
                "total_lineas"
            ],
            "30.00",
        )

        self.assertEqual(
            p[
                "warnings"
            ],
            [],
        )


    def test_old_layout_still_supported(
        self,
    ):

        h = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                OLD_LAYOUT_782
            )
        )


        self.assertEqual(
            h[
                "importe_base_imponible"
            ],
            "176.04",
        )

        self.assertEqual(
            h[
                "importe_iva"
            ],
            "36.97",
        )

        self.assertEqual(
            h[
                "iva_porcentaje"
            ],
            "21.00",
        )

        self.assertEqual(
            h[
                "importe_factura"
            ],
            "213.01",
        )


    def test_iva_orientation_by_math(
        self,
    ):

        h1 = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                REAL_LAYOUT_781
            )
        )

        h2 = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                OLD_LAYOUT_782
            )
        )


        self.assertEqual(
            h1[
                "iva_layout_detectado"
            ],
            "BRUTO_BASE_IVA_PCT",
        )

        self.assertEqual(
            h2[
                "iva_layout_detectado"
            ],
            "BRUTO_BASE_PCT_IVA",
        )


    def test_customer_number_never_invoice(
        self,
    ):

        h = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                REAL_LAYOUT_781
            )
        )

        self.assertNotEqual(
            h[
                "num_factura_proveedor"
            ],
            "430030962",
        )
