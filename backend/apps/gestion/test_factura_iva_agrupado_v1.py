
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.gestion import views


def factura(
    *,
    base="0.00",
    iva="0.00",
    retencion="0.00",
    subtipo="",
):

    return SimpleNamespace(
        importe_base_imponible=Decimal(
            base
        ),
        importe_iva=Decimal(
            iva
        ),
        retencion=Decimal(
            retencion
        ),
        subtipo_rectificativa=subtipo,
    )


def linea(
    pk,
    base,
    pct="21.00",
    **extra,
):

    raw = {
        "iva_porcentaje": pct,
    }

    raw.update(
        extra
    )


    return SimpleNamespace(
        pk=pk,
        importe_linea=Decimal(
            base
        ),
        raw_data=raw,
        factura=None,
    )


class FacturaIvaAgrupadoV1Tests(
    SimpleTestCase,
):

    def test_proinco_signed_base(
        self,
    ):

        f = factura()

        lines = [
            linea(1, "-67.00"),
            linea(2, "-37.28"),
            linea(3, "-43.00"),
            linea(4, "190.32"),
            linea(5, "62.62"),
            linea(6, "40.50"),
        ]


        result = (
            views
            ._gestion_factura_totales_agrupados_iva_v1(
                f,
                lines,
            )
        )


        self.assertEqual(
            result["base"],
            Decimal("146.16"),
        )

        self.assertEqual(
            result["iva"],
            Decimal("30.69"),
        )

        self.assertEqual(
            result["total"],
            Decimal("176.85"),
        )


    def test_positive_subset_rounds_by_group(
        self,
    ):

        f = factura()

        result = (
            views
            ._gestion_factura_totales_agrupados_iva_v1(
                f,
                [
                    linea(
                        1,
                        "190.32",
                    ),
                    linea(
                        2,
                        "62.62",
                    ),
                    linea(
                        3,
                        "40.50",
                    ),
                ],
            )
        )


        self.assertEqual(
            result["base"],
            Decimal("293.44"),
        )

        self.assertEqual(
            result["iva"],
            Decimal("61.62"),
        )


    def test_multiple_rates(
        self,
    ):

        f = factura()


        result = (
            views
            ._gestion_factura_totales_agrupados_iva_v1(
                f,
                [
                    linea(
                        1,
                        "100.00",
                        "21.00",
                    ),
                    linea(
                        2,
                        "50.00",
                        "10.00",
                    ),
                ],
            )
        )


        self.assertEqual(
            result["base"],
            Decimal("150.00"),
        )

        self.assertEqual(
            result["iva"],
            Decimal("26.00"),
        )

        self.assertEqual(
            result["total"],
            Decimal("176.00"),
        )


    def test_negative_invoice(
        self,
    ):

        f = factura()


        result = (
            views
            ._gestion_factura_totales_agrupados_iva_v1(
                f,
                [
                    linea(
                        1,
                        "-100.00",
                        "21.00",
                    ),
                ],
            )
        )


        self.assertEqual(
            result["base"],
            Decimal("-100.00"),
        )

        self.assertEqual(
            result["iva"],
            Decimal("-21.00"),
        )

        self.assertEqual(
            result["total"],
            Decimal("-121.00"),
        )


    def test_retention(
        self,
    ):

        f = factura(
            retencion="10.00",
        )


        result = (
            views
            ._gestion_factura_totales_agrupados_iva_v1(
                f,
                [
                    linea(
                        1,
                        "100.00",
                        "21.00",
                    ),
                ],
            )
        )


        self.assertEqual(
            result["total"],
            Decimal("111.00"),
        )


    def test_canonical_total_beats_polluted_legacy(
        self,
    ):

        row = linea(
            12274,
            "62.62",
            "21.00",
            importe_total_con_iva=(
                "-1360.95"
            ),
            total_con_iva=(
                "-1360.95"
            ),
            total_linea_con_iva=(
                "75.77"
            ),
        )


        total = (
            views
            ._gestion_factura_linea_total_con_iva_v1(
                row
            )
        )


        self.assertEqual(
            total,
            Decimal("75.77"),
        )


    def test_invalid_corrupt_header_not_used_as_pct(
        self,
    ):

        f = factura(
            base="146.16",
            iva="-2773.11",
        )


        row = SimpleNamespace(
            pk=1,
            importe_linea=Decimal(
                "100.00"
            ),
            raw_data={},
            factura=f,
        )


        pct = (
            views
            ._gestion_factura_linea_iva_pct_canonico_v1(
                row,
                factura=f,
            )
        )


        self.assertIsNone(
            pct
        )
