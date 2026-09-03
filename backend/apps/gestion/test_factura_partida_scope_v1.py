
import inspect

from django.test import SimpleTestCase

from apps.gestion import views


class FacturaPartidaScopeV1R2Tests(
    SimpleTestCase,
):

    def test_marker(self):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertIn(
            "FACTURA_PARTIDA_SCOPE_V1_R2",
            source,
        )


    def test_distinct_sin_ordering(self):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertIn(
            "tareas_base_qs",
            source,
        )

        self.assertIn(
            ".order_by()",
            source,
        )


    def test_post_mismo_scope(self):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertIn(
            "tareas_qs",
            source,
        )

        self.assertNotIn(
            "TareaObra.objects.filter(team=factura.team",
            source,
        )


    def test_old_scope_removed(self):

        source = inspect.getsource(
            views.factura_lineas_a_partida
        )

        self.assertNotIn(
            'filter(team=factura.team, partida__isnull=False)',
            source,
        )
