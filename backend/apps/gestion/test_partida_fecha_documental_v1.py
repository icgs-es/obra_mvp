
import inspect

from django.test import SimpleTestCase

from apps.gestion import views


class PartidaFechaDocumentalV1Tests(
    SimpleTestCase,
):

    def test_factura_default_document_date(
        self,
    ):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertIn(
            "factura.fecha_emision",
            source,
        )

        self.assertIn(
            "PARTIDA_FECHA_DOCUMENTAL_V1",
            source,
        )


    def test_albaran_default_document_date(
        self,
    ):

        source = inspect.getsource(
            views.albaran_lineas_a_partida
        )

        self.assertIn(
            "albaran.fecha_albaran",
            source,
        )

        self.assertIn(
            "PARTIDA_FECHA_DOCUMENTAL_V1",
            source,
        )


    def test_factura_no_usa_today_as_primary_default(
        self,
    ):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertIn(
            '"fecha_hoy": (',
            source,
        )

        self.assertIn(
            "factura.fecha_emision",
            source,
        )
