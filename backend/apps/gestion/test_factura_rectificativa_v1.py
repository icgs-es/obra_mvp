from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion.factura_naturaleza import (
    normalizar_factura_extraida_v1,
)

from apps.gestion.models import (
    FacturaProveedorGestion,
)


class FacturaRectificativaV1Tests(
    SimpleTestCase,
):

    def test_modelo_tiene_campos_rectificativa(self):
        fields = {
            f.name
            for f in FacturaProveedorGestion._meta.fields
        }

        self.assertTrue(
            {
                "tipo_factura",
                "subtipo_rectificativa",
                "numero_factura_rectificada",
                "factura_rectificada",
            }.issubset(fields)
        )

    def test_idaterm_abono_signo_economico(self):
        extracted = {
            "text": """
                ABONO AB26/01371
                IDATERM S.L.
                CORRESPONDE A LA FACTURA
                - FV26/07450

                Base imponible 1.583,46
                IVA 332,53
                TOTAL 1.915,99
            """,
            # Simula precisamente el fallo visual previo:
            # número lateral = factura original;
            # base ya negativa;
            # IVA y total positivos.
            "numero_documento": (
                "FV26/07450"
            ),
            "base_imponible": (
                "-1583.46"
            ),
            "iva": "332.53",
            "total": "1915.99",
        }

        initial = {
            "num_factura_proveedor": (
                "AB26/01371"
            ),
            "importe_base_imponible": (
                "-1583.46"
            ),
            "importe_iva": "332.53",
            "importe_factura": (
                "1915.99"
            ),
        }

        normalized, initial, meta = (
            normalizar_factura_extraida_v1(
                extracted,
                initial,
                original_name=(
                    "Abono No AB2601371.pdf"
                ),
            )
        )

        self.assertEqual(
            meta["tipo_factura"],
            "RECTIFICATIVA",
        )

        self.assertEqual(
            meta[
                "subtipo_rectificativa"
            ],
            "ABONO",
        )

        self.assertEqual(
            meta[
                "numero_factura_rectificada"
            ],
            "FV26/07450",
        )

        self.assertEqual(
            normalized[
                "numero_documento"
            ],
            "AB26/01371",
        )

        self.assertEqual(
            normalized[
                "base_imponible"
            ],
            "-1583.46",
        )

        self.assertEqual(
            normalized["iva"],
            "-332.53",
        )

        self.assertEqual(
            normalized["total"],
            "-1915.99",
        )

        self.assertEqual(
            meta[
                "documento_importes"
            ]["total"],
            "1915.99",
        )

        self.assertEqual(
            initial[
                "importe_factura"
            ],
            "-1915.99",
        )

    def test_rectificativa_positiva_no_se_fuerza_negativa(
        self,
    ):
        extracted = {
            "text": (
                "Factura creada "
                "(rectificación de "
                "2026-00055, "
                "eliminando el punto 3)"
            ),
            "numero_documento": (
                "2026-00057"
            ),
            "base_imponible": (
                "7238.00"
            ),
            "iva": "1519.98",
            "total": "8757.98",
        }

        normalized, _, meta = (
            normalizar_factura_extraida_v1(
                extracted
            )
        )

        self.assertEqual(
            meta["tipo_factura"],
            "RECTIFICATIVA",
        )

        self.assertEqual(
            meta[
                "subtipo_rectificativa"
            ],
            "OTRA",
        )

        self.assertEqual(
            meta[
                "numero_factura_rectificada"
            ],
            "2026-00055",
        )

        self.assertEqual(
            normalized["total"],
            "8757.98",
        )

    def test_factura_normal_permanece_normal(
        self,
    ):
        normalized, _, meta = (
            normalizar_factura_extraida_v1(
                {
                    "text": (
                        "FACTURA FV26/99999"
                    ),
                    "numero_documento": (
                        "FV26/99999"
                    ),
                    "base_imponible": (
                        "100.00"
                    ),
                    "iva": "21.00",
                    "total": "121.00",
                }
            )
        )

        self.assertEqual(
            meta["tipo_factura"],
            "NORMAL",
        )

        self.assertEqual(
            meta[
                "subtipo_rectificativa"
            ],
            "",
        )

        self.assertEqual(
            normalized["total"],
            "121.00",
        )

    def test_ocr_import_no_puede_positivizar_abono(
        self,
    ):
        """
        Contrato V2.

        Las líneas OCR nunca pueden convertir un ABONO
        en positivo.

        La cabecera económica oficial del PDF se captura
        antes de crear líneas y se restaura con signo
        negativo al finalizar la importación.
        """

        views_path = (
            Path(__file__)
            .with_name("views.py")
        )

        source = (
            views_path.read_text(
                encoding="utf-8"
            )
        )

        self.assertIn(
            "FACTURA_ABONO_OCR_HEADER_BEFORE_V2",
            source,
        )

        self.assertIn(
            "FACTURA_ABONO_OCR_HEADER_PRESERVE_V2",
            source,
        )

        self.assertIn(
            "_factura_header_before_lineas_ocr_v2",
            source,
        )

        self.assertIn(
            "factura.importe_base_imponible = -abs(",
            source,
        )

        self.assertIn(
            "factura.importe_iva = -abs(",
            source,
        )

        self.assertIn(
            "factura.importe_factura = -abs(",
            source,
        )

