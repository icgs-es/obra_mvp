
import inspect

from django.test import SimpleTestCase

from apps.gestion import views


class ValoracionDiferidaSafeLockFixV1Tests(
    SimpleTestCase
):

    def test_safe_execute_no_outer_join_under_lock(self):

        src = inspect.getsource(
            views
            ._gestion_factura_importar_desde_albaran_execute_safe_v1
        )

        self.assertIn(
            "VALORACION_DIFERIDA_SAFE_EXECUTE_LOCK_FIX_V1",
            src,
        )

        self.assertIn(
            ".select_for_update()",
            src,
        )

        self.assertNotIn(
            '.select_related(\n                "articulo_compra"',
            src,
        )

        self.assertIn(
            "articulo_compra_id",
            src,
        )

