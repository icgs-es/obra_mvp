
from decimal import Decimal

from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion.forms import (
    FacturaProveedorLineaForm,
)

from apps.gestion.services.descuento_linea import (
    calcular_linea_compra,
)


class FacturaDescuentoPorcentualSaveV2Tests(
    SimpleTestCase
):

    def test_formula_exacta_usuario(self):

        result = calcular_linea_compra(
            cantidad="4",
            precio_unitario="15",
            descuento_porcentaje="20",
            descuento_adicional="0",
        )

        self.assertEqual(
            result["base_linea"],
            Decimal("48.00"),
        )

        self.assertEqual(
            result[
                "descuento_porcentaje_importe"
            ],
            Decimal("12.00"),
        )

        self.assertEqual(
            result[
                "descuento_adicional"
            ],
            Decimal("0.00"),
        )


    def test_form_active_patch(self):

        self.assertTrue(
            getattr(
                FacturaProveedorLineaForm,
                "_gestion_descuento_porcentual_save_v2",
                False,
            )
        )


    def test_frontend_no_formula_unitaria(self):

        text = Path(
            "templates/gestion/"
            "factura_linea_form.html"
        ).read_text()

        self.assertIn(
            "FACTURA_LINEA_DESCUENTO_PORCENTUAL_SAVE_V2",
            text,
        )

        self.assertIn(
            "(1 - Dto.% / 100)",
            text,
        )

        self.assertNotIn(
            "Cant. × (Precio - Dto. unit.)",
            text,
        )

        self.assertIn(
            "q\n          * p\n          * (1 - dtoPct / 100)",
            text,
        )


    def test_detail_displays_percentage(self):

        text = Path(
            "templates/gestion/"
            "factura_detail.html"
        ).read_text()

        self.assertIn(
            "{{ l.descuento|floatformat:2 }} %",
            text,
        )

        self.assertNotIn(
            "{{ l|factura_linea_descuento_display }}",
            text,
        )

