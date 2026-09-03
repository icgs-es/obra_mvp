
from datetime import (
    date,
    timedelta,
)

from django.test import SimpleTestCase

from apps.gestion.forms import (
    FACTURA_FORMA_PAGO_DIAS,
)

from apps.gestion.forms_pagos import (
    FORMA_PAGO_CHOICES,
)


class ReciboDomiciliadoInmediatoV1Tests(
    SimpleTestCase,
):

    def test_catalogo_factura(
        self,
    ):

        values = [
            value
            for value, _days
            in FACTURA_FORMA_PAGO_DIAS
        ]

        self.assertEqual(
            values.count(
                "RECIBO DOMICILIADO"
            ),
            1,
        )


    def test_recibo_domiciliado_es_cero_dias(
        self,
    ):

        mapping = dict(
            FACTURA_FORMA_PAGO_DIAS
        )

        self.assertEqual(
            mapping[
                "RECIBO DOMICILIADO"
            ],
            0,
        )


    def test_vencimiento_es_fecha_factura(
        self,
    ):

        mapping = dict(
            FACTURA_FORMA_PAGO_DIAS
        )

        fecha = date(
            2026,
            8,
            1,
        )

        vencimiento = (
            fecha
            + timedelta(
                days=mapping[
                    "RECIBO DOMICILIADO"
                ]
            )
        )

        self.assertEqual(
            vencimiento,
            fecha,
        )


    def test_catalogo_plan_pagos(
        self,
    ):

        values = [
            value
            for value, _label
            in FORMA_PAGO_CHOICES
        ]

        self.assertEqual(
            values.count(
                "RECIBO DOMICILIADO"
            ),
            1,
        )


    def test_label_plan_pagos(
        self,
    ):

        mapping = dict(
            FORMA_PAGO_CHOICES
        )

        self.assertEqual(
            mapping[
                "RECIBO DOMICILIADO"
            ],
            "RECIBO DOMICILIADO",
        )
