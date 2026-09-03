from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services.valoracion_diferida_fuentes import (
    evaluar_fuente_economica,
    sumar_base_lineas,
)


class ValoracionDiferidaFuentesV1Tests(SimpleTestCase):

    def test_fuente_confiable(self):

        parsed = {
            "lineas": [
                {
                    "importe": "100.00",
                },
                {
                    "importe_linea": "52.00",
                },
            ]
        }

        r = evaluar_fuente_economica(
            factura_base="152.00",
            parsed=parsed,
        )

        self.assertEqual(
            r["estado"],
            "CONFIABLE",
        )

        self.assertTrue(
            r["auto_aplicar"]
        )

        self.assertEqual(
            r["diferencia"],
            Decimal("0.00"),
        )


    def test_fuente_inconsistente(self):

        parsed = {
            "lineas": [
                {
                    "importe": "0.00",
                }
            ]
        }

        r = evaluar_fuente_economica(
            factura_base="888.24",
            parsed=parsed,
        )

        self.assertEqual(
            r["estado"],
            "INCONSISTENTE",
        )

        self.assertFalse(
            r["auto_aplicar"]
        )

        self.assertEqual(
            r["diferencia"],
            Decimal("888.24"),
        )


    def test_sin_lineas(self):

        r = evaluar_fuente_economica(
            factura_base="100.00",
            parsed={
                "lineas": [],
            },
        )

        self.assertEqual(
            r["estado"],
            "SIN_DATOS",
        )

        self.assertFalse(
            r["auto_aplicar"]
        )


    def test_linea_sin_importe_es_incompleta(self):

        parsed = {
            "lineas": [
                {
                    "descripcion": "A",
                    "importe": "10.00",
                },
                {
                    "descripcion": "B",
                },
            ]
        }

        r = evaluar_fuente_economica(
            factura_base="20.00",
            parsed=parsed,
        )

        self.assertEqual(
            r["estado"],
            "INCOMPLETA",
        )

        self.assertFalse(
            r["auto_aplicar"]
        )


    def test_importe_cero_explicito_cuenta_como_importe(self):

        base, count = sumar_base_lineas(
            [
                {
                    "precio": "100",
                    "descuento": "100",
                    "importe": "0.00",
                },
                {
                    "importe": "25.00",
                },
            ]
        )

        self.assertEqual(
            base,
            Decimal("25.00"),
        )

        self.assertEqual(
            count,
            2,
        )


    def test_negativo_participa_en_base(self):

        base, count = sumar_base_lineas(
            [
                {
                    "importe": "100.00",
                },
                {
                    "importe": "-20.00",
                },
            ]
        )

        self.assertEqual(
            base,
            Decimal("80.00"),
        )

        self.assertEqual(
            count,
            2,
        )


    def test_tolerancia_redondeo(self):

        parsed = {
            "lineas": [
                {
                    "importe": "50.01",
                },
                {
                    "importe": "49.98",
                },
            ]
        }

        r = evaluar_fuente_economica(
            factura_base="100.00",
            parsed=parsed,
        )

        self.assertEqual(
            r["estado"],
            "CONFIABLE",
        )

        self.assertEqual(
            r["diferencia"],
            Decimal("0.01"),
        )
