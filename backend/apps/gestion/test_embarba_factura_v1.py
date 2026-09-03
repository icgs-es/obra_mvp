
import inspect

from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services import (
    facturas_pdf,
)


EMBARBA_TEXT = """
A.EMBARBA, S.A. -A29018637 - Registro Mercantil de Málaga
ADRI MARTIN INVESMENT S.L.
R26 143.782 01/08/2026 B93578649
FACTURA FECHA FACTURA
430030962
CANTIDAD C O N C E P T O IMPORTE
Página 1 de 1
POR EL SERVICIO DE MANTENIMIENTO EN EL/LOS ASCENSOR/ES
CORRESPONDIENTES AL MES DE AGOSTO
Bloque I (izq) - Urb. AltoVeloo
Bloque J - Urb. AltoVeloo
MANTENIMIENTO PLATINUM 160,00
ARRENDAMIENTO MODULAR 5,60
SERVICIO DE COMUNICACION BIDIRECCIONAL 10,44
A partir del 1 de Julio de 2024, A. Embarba, S.A. realizará la comunicación
y el envío de los trabajos de mantenimiento mensuales.
Total Bruto Exento
176,04 176,04 21,00 36,97
Bases Iva % Iva Cuota Iva % Retenc. Retención
0,00 0,00
Factura domiciliada en BANCO SANTANDER S.A.
Incluido Servicio 24 Horas de Emergencias y Rescate de Personas
TOTAL FACTURA
% Irpf Cuota Irpf
213,01
"""


class EmbarbaFacturaValoradaV1R1Tests(
    SimpleTestCase,
):

    def test_header_real(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                EMBARBA_TEXT
            )
        )


        self.assertEqual(
            result[
                "num_factura_proveedor"
            ],
            "R26 143.782",
        )

        self.assertEqual(
            result[
                "fecha_emision"
            ],
            "01/08/2026",
        )

        self.assertEqual(
            result[
                "fecha_iso"
            ],
            "2026-08-01",
        )

        self.assertEqual(
            result[
                "importe_base_imponible"
            ],
            "176.04",
        )

        self.assertEqual(
            result[
                "iva_porcentaje"
            ],
            "21.00",
        )

        self.assertEqual(
            result[
                "importe_iva"
            ],
            "36.97",
        )

        self.assertEqual(
            result[
                "importe_factura"
            ],
            "213.01",
        )


    def test_customer_number_is_not_invoice(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_header_v1(
                EMBARBA_TEXT
            )
        )

        self.assertNotEqual(
            result[
                "num_factura_proveedor"
            ],
            "430030962",
        )


    def test_exact_three_lines(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_lines_v1(
                EMBARBA_TEXT
            )
        )


        self.assertEqual(
            len(
                result[
                    "lineas"
                ]
            ),
            3,
        )

        self.assertEqual(
            result[
                "total_lineas"
            ],
            "176.04",
        )

        self.assertEqual(
            result[
                "warnings"
            ],
            [],
        )


    def test_line_values(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_lines_v1(
                EMBARBA_TEXT
            )
        )


        actual = [
            (
                row[
                    "descripcion"
                ],
                row[
                    "cantidad"
                ],
                row[
                    "precio_unitario"
                ],
                row[
                    "importe_linea"
                ],
            )
            for row
            in result[
                "lineas"
            ]
        ]


        expected = [
            (
                "MANTENIMIENTO PLATINUM",
                "1.0000",
                "160.0000",
                "160.00",
            ),
            (
                "ARRENDAMIENTO MODULAR",
                "1.0000",
                "5.6000",
                "5.60",
            ),
            (
                (
                    "SERVICIO DE COMUNICACION "
                    "BIDIRECCIONAL"
                ),
                "1.0000",
                "10.4400",
                "10.44",
            ),
        ]


        self.assertEqual(
            actual,
            expected,
        )


    def test_lines_reconcile_base(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_lines_v1(
                EMBARBA_TEXT
            )
        )


        total = sum(
            Decimal(
                row[
                    "importe_linea"
                ]
            )
            for row
            in result[
                "lineas"
            ]
        )


        self.assertEqual(
            total,
            Decimal("176.04"),
        )


    def test_descriptive_text_excluded(
        self,
    ):

        result = (
            facturas_pdf
            ._portal_embarba_extract_lines_v1(
                EMBARBA_TEXT
            )
        )


        joined = " ".join(
            row[
                "descripcion"
            ]
            for row
            in result[
                "lineas"
            ]
        ).upper()


        for token in (
            "POR EL SERVICIO",
            "CORRESPONDIENTES AL MES",
            "BLOQUE I",
            "JULIO DE 2024",
        ):

            self.assertNotIn(
                token,
                joined,
            )


    def test_payload_routing(
        self,
    ):

        payload = {
            "numero_documento": (
                "430030962"
            ),

            "base_imponible": None,
            "iva": None,
            "total": "213.01",

            "text": (
                EMBARBA_TEXT
            ),
        }


        result = (
            facturas_pdf
            .apply_factura_payload_by_template_v1(
                payload,
                parser_key=(
                    "embarba_factura_valorada_v1"
                ),
            )
        )


        self.assertEqual(
            result[
                "numero_documento"
            ],
            "R26 143.782",
        )

        self.assertEqual(
            result[
                "base_imponible"
            ],
            "176.04",
        )

        self.assertEqual(
            result[
                "iva"
            ],
            "36.97",
        )

        self.assertEqual(
            result[
                "total"
            ],
            "213.01",
        )

        self.assertEqual(
            len(
                result[
                    "lineas"
                ]
            ),
            3,
        )


    def test_line_dispatcher_embarba(
        self,
    ):

        result = (
            facturas_pdf
            .extract_factura_lines_by_template_v1(
                EMBARBA_TEXT,
                parser_key=(
                    "embarba_factura_valorada_v1"
                ),
            )
        )


        self.assertEqual(
            result[
                "parser_key"
            ],
            "embarba_factura_valorada_v1",
        )

        self.assertEqual(
            len(
                result[
                    "lineas"
                ]
            ),
            3,
        )


    def test_active_dispatcher_preserves_existing_routes(
        self,
    ):

        source = inspect.getsource(
            facturas_pdf
            .extract_factura_lines_by_template_v1
        )


        for token in (
            "embarba_factura_valorada_v1",
            "luzar_factura_valorada_v1",
            "manolillo_factura_valorada_v1",
            "joma_factura_valorada_v1",
            "idaterm_factura_valorada_v1",
            (
                "_portal_idaterm_factura_"
                "abono_extract_lines_v1"
            ),
        ):

            self.assertIn(
                token,
                source,
            )


    def test_unknown_template_preserved(
        self,
    ):

        payload = {
            "numero_documento": "X",
            "total": "10.00",
        }


        result = (
            facturas_pdf
            .apply_factura_payload_by_template_v1(
                payload.copy(),
                parser_key="unknown",
            )
        )


        self.assertEqual(
            result,
            payload,
        )
