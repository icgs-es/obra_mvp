from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion.services.valoracion_diferida import (
    normalizar_linea_factura,
    reconciliar_lineas,
    resumen_reconciliacion,
)


class ValoracionDiferidaEngineV1Tests(SimpleTestCase):

    def test_una_linea_sin_valorar_match_exacto(self):

        alb = [{
            "id": 1,
            "descripcion": "MORTERO M5",
            "cantidad": "10",
            "unidad": "UD",
            "precio": "0",
            "importe": "0",
            "sin_valorar_albaran": True,
        }]

        fac = [{
            "descripcion": "MORTERO M5",
            "cantidad": "10",
            "unidad": "UD",
            "precio": "2.50",
            "descuento": "0",
            "importe": "25.00",
        }]

        r = reconciliar_lineas(alb, fac)

        self.assertEqual(
            r[0]["estado_match"],
            "MATCH_EXACTO",
        )

        self.assertEqual(
            r[0]["estado_valoracion"],
            "VALORADA_EN_FACTURA",
        )

        self.assertTrue(
            r[0]["auto_aplicable"]
        )


    def test_todas_sin_valorar(self):

        alb = [
            {
                "descripcion": "A",
                "cantidad": "2",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            },
            {
                "descripcion": "B",
                "cantidad": "3",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            },
        ]

        fac = [
            {
                "descripcion": "A",
                "cantidad": "2",
                "unidad": "UD",
                "precio": "5",
                "importe": "10",
            },
            {
                "descripcion": "B",
                "cantidad": "3",
                "unidad": "UD",
                "precio": "7",
                "importe": "21",
            },
        ]

        r = reconciliar_lineas(
            alb,
            fac,
        )

        s = resumen_reconciliacion(r)

        self.assertEqual(
            s["total"],
            2,
        )

        self.assertEqual(
            s["auto_aplicables"],
            2,
        )


    def test_mezcla_valorada_y_sin_valorar(self):

        alb = [
            {
                "descripcion": "A",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "10",
                "importe": "10",
            },
            {
                "descripcion": "B",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "0",
                "importe": "0",
                "sin_valorar_albaran": True,
            },
        ]

        fac = [
            {
                "descripcion": "A",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "10",
                "importe": "10",
            },
            {
                "descripcion": "B",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "20",
                "importe": "20",
            },
        ]

        r = reconciliar_lineas(
            alb,
            fac,
        )

        self.assertEqual(
            len(r),
            2,
        )

        self.assertTrue(
            r[1]["auto_aplicable"]
        )


    def test_descuento_100_es_valoracion_explicita(self):

        f = normalizar_linea_factura({
            "descripcion": "SERVICIO BONIFICADO",
            "cantidad": "1",
            "unidad": "UD",
            "precio": "100",
            "descuento": "100",
            "importe": "0",
        })

        self.assertEqual(
            f["precio"],
            Decimal("100.0000"),
        )

        self.assertEqual(
            f["importe"],
            Decimal("0.00"),
        )

        self.assertEqual(
            f["descuento"],
            Decimal("100"),
        )

        self.assertTrue(
            f["valoracion_explicita"]
        )


    def test_precio_ausente_no_es_cero_explicito(self):

        f = normalizar_linea_factura({
            "descripcion": "MATERIAL",
            "cantidad": "1",
            "unidad": "UD",
            "importe": "20",
        })

        self.assertIsNone(
            f["precio"]
        )

        self.assertFalse(
            f["valoracion_explicita"]
        )


    def test_diferencia_cantidad_bloquea_auto(self):

        alb = [{
            "descripcion": "PERFIL",
            "cantidad": "180",
            "unidad": "UD",
            "precio": "0",
            "importe": "0",
            "sin_valorar_albaran": True,
        }]

        fac = [{
            "descripcion": "PERFIL",
            "cantidad": "540",
            "unidad": "UD",
            "precio": "4.01",
            "descuento": "66",
            "importe": "736.24",
        }]

        r = reconciliar_lineas(
            alb,
            fac,
        )

        self.assertEqual(
            r[0]["estado_valoracion"],
            "DIFERENCIA_CANTIDAD",
        )

        self.assertFalse(
            r[0]["auto_aplicable"]
        )


    def test_diferencia_unidad_bloquea_auto(self):

        alb = [{
            "descripcion": "PERFIL",
            "cantidad": "10",
            "unidad": "UD",
            "precio": "0",
            "importe": "0",
            "sin_valorar_albaran": True,
        }]

        fac = [{
            "descripcion": "PERFIL",
            "cantidad": "10",
            "unidad": "ML",
            "precio": "4",
            "importe": "40",
        }]

        r = reconciliar_lineas(
            alb,
            fac,
        )

        self.assertEqual(
            r[0]["estado_valoracion"],
            "DIFERENCIA_UNIDAD",
        )

        self.assertFalse(
            r[0]["auto_aplicable"]
        )


    def test_importe_negativo_es_economia_valida(self):

        f = normalizar_linea_factura({
            "descripcion": "ABONO",
            "cantidad": "-1",
            "unidad": "UD",
            "precio": "10",
            "descuento": "0",
            "importe": "-10",
        })

        self.assertTrue(
            f["valoracion_explicita"]
        )

        self.assertEqual(
            f["importe"],
            Decimal("-10.00"),
        )


    def test_match_ambiguo_no_se_aplica(self):

        alb = [{
            "descripcion": "TORNILLO",
            "cantidad": "1",
            "unidad": "UD",
            "precio": "0",
            "importe": "0",
            "sin_valorar_albaran": True,
        }]

        fac = [
            {
                "descripcion": "TORNILLO",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "1",
                "importe": "1",
            },
            {
                "descripcion": "TORNILLO",
                "cantidad": "1",
                "unidad": "UD",
                "precio": "2",
                "importe": "2",
            },
        ]

        r = reconciliar_lineas(
            alb,
            fac,
        )

        self.assertEqual(
            r[0]["estado_match"],
            "MATCH_AMBIGUO",
        )

        self.assertFalse(
            r[0]["auto_aplicable"]
        )
