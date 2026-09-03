
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.gestion import views


class AlbaranPartidaCosteNetoV1Tests(
    SimpleTestCase,
):

    def test_descuento_76(
        self,
    ):
        linea = SimpleNamespace(
            cantidad=Decimal("3.0000"),
            precio_unitario=Decimal("97.8800"),
            descuento=Decimal("76.0000"),
            importe_descuento=Decimal("0.00"),
            importe_linea=Decimal("70.47"),
        )

        result = (
            views._gestion_linea_precio_real_neto_v1(
                linea
            )
        )

        self.assertEqual(
            result,
            Decimal("23.4900"),
        )


    def test_sin_descuento(
        self,
    ):
        linea = SimpleNamespace(
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("10.0000"),
            descuento=Decimal("0"),
            importe_descuento=Decimal("0"),
            importe_linea=Decimal("20.00"),
        )

        self.assertEqual(
            views._gestion_linea_precio_real_neto_v1(
                linea
            ),
            Decimal("10.0000"),
        )


    def test_descuento_100(
        self,
    ):
        linea = SimpleNamespace(
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("50.0000"),
            descuento=Decimal("100.0000"),
            importe_descuento=Decimal("0"),
            importe_linea=Decimal("0.00"),
        )

        self.assertEqual(
            views._gestion_linea_precio_real_neto_v1(
                linea
            ),
            Decimal("0.0000"),
        )


    def test_descuento_adicional(
        self,
    ):
        linea = SimpleNamespace(
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("10.0000"),
            descuento=Decimal("10.0000"),
            importe_descuento=Decimal("2.00"),
            importe_linea=Decimal("16.00"),
        )

        self.assertEqual(
            views._gestion_linea_precio_real_neto_v1(
                linea
            ),
            Decimal("8.0000"),
        )


    def test_historico_incompleto_fallback_bruto(
        self,
    ):
        linea = SimpleNamespace(
            cantidad=Decimal("2.0000"),
            precio_unitario=Decimal("10.0000"),
            descuento=Decimal("0"),
            importe_descuento=Decimal("0"),
            importe_linea=Decimal("0.00"),
        )

        self.assertEqual(
            views._gestion_linea_precio_real_neto_v1(
                linea
            ),
            Decimal("10.0000"),
        )
