from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.gestion.services.descuento_linea import (
    calcular_linea_compra,
)


class DescuentoPorcentualCanonicoV1Tests(
    SimpleTestCase
):
    def calc(
        self,
        cantidad,
        precio,
        descuento="0",
        adicional="0",
    ):
        return calcular_linea_compra(
            cantidad=cantidad,
            precio_unitario=precio,
            descuento_porcentaje=descuento,
            descuento_adicional=adicional,
        )

    def test_dos_por_diez_descuento_veinte(self):
        resultado = self.calc(
            "2",
            "10.00",
            "20",
        )
        self.assertEqual(
            resultado["base_linea"],
            Decimal("16.00"),
        )

    def test_precio_sin_descuento(self):
        resultado = self.calc(
            "1",
            "38.59",
            "0",
        )
        self.assertEqual(
            resultado["base_linea"],
            Decimal("38.59"),
        )

    def test_descuento_cien_por_ciento(self):
        resultado = self.calc(
            "1",
            "38.59",
            "100",
        )
        self.assertEqual(
            resultado["base_linea"],
            Decimal("0.00"),
        )

    def test_devolucion_negativa(self):
        resultado = self.calc(
            "-12",
            "2.066",
            "20",
        )
        self.assertEqual(
            resultado["base_linea"],
            Decimal("-19.83"),
        )

    def test_descuento_adicional(self):
        resultado = self.calc(
            "2",
            "10.00",
            "20",
            "1.50",
        )
        self.assertEqual(
            resultado["base_linea"],
            Decimal("14.50"),
        )

    def test_rechaza_mas_de_cien(self):
        with self.assertRaises(
            ValidationError
        ):
            self.calc(
                "1",
                "10",
                "100.01",
            )

    def test_factura_usa_porcentaje(self):
        text = Path(
            "templates/gestion/"
            "factura_linea_form.html"
        ).read_text()

        self.assertIn(
            "1 - (dtoUnit / 100)",
            text,
        )
        self.assertNotIn(
            "qty * (price - dtoUnit)",
            text,
        )
        self.assertIn(
            "Importe descuento adicional (€)",
            text,
        )

    def test_albaran_usa_porcentaje(self):
        text = Path(
            "templates/gestion/"
            "albaran_linea_form.html"
        ).read_text()

        self.assertIn(
            "bruto * (1 - descuentoPct / 100)",
            text,
        )
        self.assertNotIn(
            "descuentoImporte = "
            "bruto * descuentoPct / 100",
            text,
        )
        self.assertIn(
            "Importe descuento adicional (€)",
            text,
        )

    def test_compat_tiene_descuento_adicional(self):
        text = Path(
            "templates/gestion/"
            "albaran_linea_form_compat.html"
        ).read_text()

        self.assertIn(
            'name="importe_descuento"',
            text,
        )
        self.assertIn(
            "base - dto - adicional",
            text,
        )

    def test_memoria_excluye_cien_por_ciento(self):
        text = Path(
            "apps/gestion/views.py"
        ).read_text()

        self.assertGreaterEqual(
            text.count(
                "exclude(descuento__gte=100)"
            ),
            2,
        )
