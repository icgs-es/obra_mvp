from django.test import SimpleTestCase

from apps.gestion.services.facturas_pdf import (
    _portal_ms_metales_extract_header_v2,
    _portal_ms_metales_extract_lines_v2,
)


class MsMetalesFactura202600073Test(SimpleTestCase):

    TEXT_LAYOUT = """
FACTURA
2026-00073

Fecha de emisión                                              Fecha de vencimiento
04/08/2026                                                    07/08/2026

Emisor                                                        Destinatario
JOSE ANTONIO MUÑOZ SECILLA                                    INVERADRIDE GESTION S.L
26970284r                                                     B02703833
Calle Adonis 11, 29590, Málaga, España                        CL HEROES DE SOSTOA 166, 29003, Málaga,
                                                              Málaga, España

Descripción
Suministro y tratamiento (imprimación y lacado) de placa de anclaje con garrotas y poste con
argolla.

Detalle de la facturación

 Placa de anclaje 300x200 con 4
 garrotas (Ø16 mm, 600 mm) y
                                             14        202,07 €     2.829,00 €      21%    594,09 €    3.423,09 €
 poste redondo (Ø140 mm, 2300
 mm) con argolla


 Imprimación y lacado al horno               1        1.050,00 €    1.050,00 €      21%    220,50 €    1.270,50 €


                                                                             Base imponible:          3.879,00 €
                                                                                   IVA total:          814,59 €
                                                                      TOTAL FACTURA:              4.693,59 €

Por favor, pague el importe pendiente dentro de los próximos 3 días a la cuenta bancaria.
"""

    def test_header_real_layout(self):
        h = _portal_ms_metales_extract_header_v2(
            self.TEXT_LAYOUT
        )

        self.assertEqual(
            h["num_factura_proveedor"],
            "2026-00073",
        )
        self.assertEqual(
            h["fecha_emision"],
            "2026-08-04",
        )
        self.assertEqual(
            h["vencimiento"],
            "2026-08-07",
        )
        self.assertEqual(
            h["importe_base_imponible"],
            "3879.00",
        )
        self.assertEqual(
            h["importe_iva"],
            "814.59",
        )
        self.assertEqual(
            h["importe_factura"],
            "4693.59",
        )

    def test_lines_real_layout(self):
        p = _portal_ms_metales_extract_lines_v2(
            self.TEXT_LAYOUT
        )

        self.assertEqual(len(p["lineas"]), 2)
        self.assertEqual(
            p["total_lineas"],
            "3879.00",
        )
        self.assertEqual(
            p["raw"]["total_iva_lineas"],
            "814.59",
        )
        self.assertEqual(p["warnings"], [])

        l1, l2 = p["lineas"]

        self.assertEqual(
            l1["descripcion"],
            (
                "Placa de anclaje 300x200 con 4 "
                "garrotas (Ø16 mm, 600 mm) y "
                "poste redondo (Ø140 mm, 2300 mm) "
                "con argolla"
            ),
        )
        self.assertEqual(l1["cantidad"], "14.0000")
        self.assertEqual(
            l1["precio_unitario"],
            "202.0700",
        )
        self.assertEqual(
            l1["importe_linea"],
            "2829.00",
        )
        self.assertEqual(
            l1["importe_iva_linea"],
            "594.09",
        )
        self.assertEqual(
            l1["total_linea_con_iva"],
            "3423.09",
        )

        self.assertEqual(
            l2["descripcion"],
            "Imprimación y lacado al horno",
        )
        self.assertEqual(l2["cantidad"], "1.0000")
        self.assertEqual(
            l2["precio_unitario"],
            "1050.0000",
        )
        self.assertEqual(
            l2["importe_linea"],
            "1050.00",
        )
        self.assertEqual(
            l2["importe_iva_linea"],
            "220.50",
        )
        self.assertEqual(
            l2["total_linea_con_iva"],
            "1270.50",
        )

    def test_direct_text_without_leading_indent(self):
        text = """
FACTURA
2026-00073
Fecha de emisión
04/08/2026
Fecha de vencimiento
07/08/2026
JOSE ANTONIO MUÑOZ SECILLA
26970284r
Detalle de la facturación
Placa de anclaje 300x200 con 4
garrotas (Ø16 mm, 600 mm) y
poste redondo (Ø140 mm, 2300
mm) con argolla
14 202,07 € 2.829,00 € 21% 594,09 € 3.423,09 €
Imprimación y lacado al horno 1 1.050,00 € 1.050,00 € 21% 220,50 € 1.270,50 €
Base imponible: 3.879,00 €
IVA total: 814,59 €
TOTAL FACTURA: 4.693,59 €
"""

        p = _portal_ms_metales_extract_lines_v2(
            text
        )

        self.assertEqual(len(p["lineas"]), 2)
        self.assertEqual(p["total_lineas"], "3879.00")
        self.assertEqual(
            p["raw"]["total_iva_lineas"],
            "814.59",
        )
        self.assertEqual(p["warnings"], [])

        self.assertEqual(
            p["lineas"][0]["descripcion"],
            (
                "Placa de anclaje 300x200 con 4 "
                "garrotas (Ø16 mm, 600 mm) y "
                "poste redondo (Ø140 mm, 2300 mm) "
                "con argolla"
            ),
        )

        self.assertEqual(
            p["lineas"][1]["descripcion"],
            "Imprimación y lacado al horno",
        )

    def test_historical_v_code_still_works(self):
        text = """
FACTURA 2026-00072
JOSE ANTONIO MUÑOZ SECILA 26970284R
Fecha de factura 01/08/2026
Fecha de vencimiento 05/08/2026
Detalle de la facturación
V23 Trabajo realizado. 2 10,00 € 20,00 € 21% 4,20 € 24,20 €
Base imponible: 20,00 €
IVA total: 4,20 €
TOTAL FACTURA: 24,20 €
"""

        p = _portal_ms_metales_extract_lines_v2(text)

        self.assertEqual(len(p["lineas"]), 1)
        self.assertEqual(
            p["lineas"][0]["codigo"],
            "V23",
        )
        self.assertEqual(
            p["total_lineas"],
            "20.00",
        )
