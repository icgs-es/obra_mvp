
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion import views

from apps.gestion.services.valoracion_diferida import (
    reconciliar_lineas,
    resumen_reconciliacion,
)


class ValoracionDiferidaUnitsPreviewV1Tests(
    SimpleTestCase
):

    def test_normalizador_preserva_unidades(self):

        item = (
            views
            ._gestion_norm_linea_import_albaran_v1(
                {
                    "linea": 1,
                    "descripcion": "MATERIAL",
                    "cantidad": "2",
                    "cantidad_compra": "2",
                    "unidad": "UD",
                    "unidad_compra": "UD",
                    "precio": "0",
                    "importe": "0",
                }
            )
        )

        self.assertEqual(
            item["unidad"],
            "UD",
        )

        self.assertEqual(
            item["unidad_compra"],
            "UD",
        )


    def test_misma_cantidad_misma_unidad(self):

        r = reconciliar_lineas(
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "PORTE",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            }],
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "PORTE",
                "precio": "152",
                "descuento": "0",
                "importe": "152",
            }],
        )[0]

        self.assertEqual(
            r["estado_valoracion"],
            "VALORADA_EN_FACTURA",
        )

        self.assertTrue(
            r["auto_aplicable"]
        )


    def test_unidad_albaran_no_informada(self):

        r = reconciliar_lineas(
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            }],
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "PORTE",
                "precio": "152",
                "importe": "152",
            }],
        )[0]

        self.assertEqual(
            r["estado_valoracion"],
            "UNIDAD_NO_INFORMADA_ALBARAN",
        )

        self.assertFalse(
            r["auto_aplicable"]
        )


    def test_diferencia_cantidad(self):

        r = reconciliar_lineas(
            [{
                "descripcion": "MATERIAL",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            }],
            [{
                "descripcion": "MATERIAL",
                "cantidad": "2",
                "unidad": "UD",
                "precio": "5",
                "importe": "10",
            }],
        )[0]

        self.assertEqual(
            r["estado_valoracion"],
            "DIFERENCIA_CANTIDAD",
        )


    def test_diferencia_unidad(self):

        r = reconciliar_lineas(
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            }],
            [{
                "descripcion": "PORTE",
                "cantidad": "1",
                "unidad": "PORTE",
                "precio": "152",
                "importe": "152",
            }],
        )[0]

        self.assertEqual(
            r["estado_valoracion"],
            "DIFERENCIA_UNIDAD",
        )


    def test_diferencia_cantidad_y_unidad(self):

        resultado = reconciliar_lineas(
            [{
                "descripcion": "PERFIL",
                "cantidad": "180",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            }],
            [{
                "descripcion": "PERFIL",
                "cantidad": "540",
                "unidad": "PERFIL",
                "precio": "4.01",
                "descuento": "66",
                "importe": "736.24",
            }],
        )

        r = resultado[0]

        self.assertEqual(
            r["estado_valoracion"],
            "DIFERENCIA_CANTIDAD_Y_UNIDAD",
        )

        self.assertFalse(
            r["auto_aplicable"]
        )

        s = resumen_reconciliacion(
            resultado
        )

        self.assertEqual(
            s["diferencia_cantidad"],
            1,
        )

        self.assertEqual(
            s["diferencia_unidad"],
            1,
        )

        self.assertEqual(
            s["diferencia_cantidad_y_unidad"],
            1,
        )


    def test_template_preview_segura(self):

        text = Path(
            "templates/gestion/"
            "factura_importar_desde_albaran.html"
        ).read_text()

        self.assertIn(
            "VALORACION_DIFERIDA_PREVIEW_UI_V1",
            text,
        )

        self.assertIn(
            "Conciliación factura ↔ albarán activa",
            text,
        )

        self.assertIn(
            "Valor conocido en albarán",
            text,
        )

        self.assertIn(
            "Cantidades documentales secundarias",
            text,
        )

        self.assertIn(
            "importación bloqueada",
            text,
        )

