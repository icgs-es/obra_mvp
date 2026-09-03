
import inspect
from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion import views


class ValoracionDiferidaSafeExecuteV1Tests(
    SimpleTestCase
):

    def test_decimal_espanol(self):

        parser = (
            views
            ._gestion_vd_decimal_strict_v1
        )

        self.assertEqual(
            str(
                parser(
                    "4,01",
                    "precio",
                )
            ),
            "4.01",
        )

        self.assertEqual(
            str(
                parser(
                    "540,0000",
                    "cantidad",
                )
            ),
            "540.0000",
        )

        self.assertEqual(
            str(
                parser(
                    "4.0100",
                    "precio",
                )
            ),
            "4.0100",
        )


    def test_safe_execute_no_crea_aliases(self):

        src = inspect.getsource(
            views
            ._gestion_factura_importar_desde_albaran_execute_safe_v1
        )

        self.assertNotIn(
            "get_or_create_articulo_alias_desde_ocr",
            src,
        )

        self.assertIn(
            "articulo_compra",
            src,
        )


    def test_safe_execute_preserva_header(self):

        src = inspect.getsource(
            views
            ._gestion_factura_importar_desde_albaran_execute_safe_v1
        )

        self.assertIn(
            "header_before",
            src,
        )

        self.assertNotIn(
            "factura_locked.importe_base_imponible =",
            src,
        )

        self.assertNotIn(
            "factura_locked.importe_iva =",
            src,
        )

        self.assertNotIn(
            "factura_locked.importe_factura =",
            src,
        )


    def test_template_editable(self):

        text = Path(
            "templates/gestion/"
            "factura_importar_desde_albaran.html"
        ).read_text()

        self.assertIn(
            "VALORACION_DIFERIDA_EDITABLE_SAFE_EXECUTE_V1",
            text,
        )

        self.assertIn(
            "vd_precio_",
            text,
        )

        self.assertIn(
            "vd_confirm_",
            text,
        )

        self.assertIn(
            "conciliar_importar",
            text,
        )

        self.assertIn(
            "Confirmar conciliación e importar",
            text,
        )


    def test_dos_rutas_post_safe(self):

        source = Path(
            "apps/gestion/views.py"
        ).read_text()

        self.assertEqual(
            source.count(
                'request.POST.get("accion") '
                '== "conciliar_importar"'
            ),
            2,
        )

