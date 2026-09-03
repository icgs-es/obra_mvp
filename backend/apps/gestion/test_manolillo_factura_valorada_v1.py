from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    _portal_manolillo_extract_header_v1,
    _portal_manolillo_extract_lines_v1,
)


class ManolilloFacturaValoradaV1Tests(
    SimpleTestCase,
):

    REAL_TEXT = """
    MANOLILLO 2006, S.L.U.
    C.I.F.: B-92.738.350
    Cortijo Blanco, 16
    29738 Torre de Benagalbón (Málaga)
    Nº Factura 090/2026
    Fecha 31/072026
    Cantidad Precio Unitario Total
    6 Contenedores mezclado de 12 M3 500,000 3.000,00 €
    Base Imponible 3.000,00 €
    IVA 21% 630,00 €
    TOTAL 3.630,00 €
    CC: ES97 30580731692720817307
    Descripción
    Obra: Lo Cea Alto Velo
    Adri Martin Investments SL
    """


    def test_header_real(
        self,
    ):

        h = (
            _portal_manolillo_extract_header_v1(
                self.REAL_TEXT
            )
        )


        self.assertEqual(
            h[
                "num_factura_proveedor"
            ],
            "090/2026",
        )


        self.assertEqual(
            h[
                "fecha_emision"
            ],
            "31/07/2026",
        )


        self.assertEqual(
            h[
                "fecha_iso"
            ],
            "2026-07-31",
        )


        self.assertEqual(
            h[
                "importe_base_imponible"
            ],
            "3000.00",
        )


        self.assertEqual(
            h[
                "importe_iva"
            ],
            "630.00",
        )


        self.assertEqual(
            h[
                "importe_factura"
            ],
            "3630.00",
        )


        self.assertEqual(
            h[
                "iva_porcentaje"
            ],
            "21.00",
        )


    def test_one_real_line(
        self,
    ):

        parsed = (
            _portal_manolillo_extract_lines_v1(
                self.REAL_TEXT
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
            "",
        )


        self.assertEqual(
            line["descripcion"],
            "Contenedores mezclado de 12 M3",
        )


        self.assertEqual(
            line["cantidad"],
            "6.0000",
        )


        self.assertEqual(
            line["precio"],
            "500.0000",
        )


        self.assertEqual(
            line["importe"],
            "3000.00",
        )


        self.assertEqual(
            parsed[
                "total_lineas"
            ],
            "3000.00",
        )


        self.assertEqual(
            parsed[
                "raw"
            ][
                "total_iva_lineas"
            ],
            "630.00",
        )
