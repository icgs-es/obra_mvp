import inspect
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.gestion import factura_cierre
from apps.gestion import forms
from apps.gestion import views


class FacturaPagadaEditableV2Tests(
    SimpleTestCase,
):

    def test_form_no_fabrica_pago_por_estado(
        self,
    ):
        import ast

        # -------------------------------------------------------------
        # 1. Validación estructural:
        #
        # Localizar el clean DEFINIDO dentro de FacturaProveedorForm,
        # no los wrappers que se instalan después.
        # -------------------------------------------------------------

        forms_path = Path(
            forms.__file__
        )

        module_source = forms_path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            module_source
        )


        class_nodes = [
            node
            for node in tree.body
            if (
                isinstance(node, ast.ClassDef)
                and node.name
                == "FacturaProveedorForm"
            )
        ]


        self.assertEqual(
            len(class_nodes),
            1,
        )


        clean_nodes = [
            node
            for node in class_nodes[0].body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name == "clean"
            )
        ]


        self.assertEqual(
            len(clean_nodes),
            1,
        )


        business_source = (
            ast.get_source_segment(
                module_source,
                clean_nodes[0],
            )
            or ""
        )


        self.assertIn(
            "FACTURA_ESTADO_PAGADA_SYNC_BACKEND_V2",
            business_source,
        )

        self.assertIn(
            "factura_pagada_explicitamente",
            business_source,
        )

        self.assertNotIn(
            "FACTURA_ESTADO_PAGADA_SYNC_BACKEND_V1",
            business_source,
        )


        # -------------------------------------------------------------
        # 2. Validación runtime:
        #
        # PLAN_CANONICO apunta a un wrapper generado por _make_clean.
        # Ese wrapper conserva el clean REAL en su closure "orig_clean".
        # -------------------------------------------------------------

        required_wrapper = getattr(
            forms,
            "_factura_plan_canonico_original_clean_v1b",
            None,
        )


        self.assertIsNotNone(
            required_wrapper
        )


        freevars = (
            required_wrapper
            .__code__
            .co_freevars
        )

        closure = (
            required_wrapper
            .__closure__
            or ()
        )


        closure_map = {
            name: cell.cell_contents
            for name, cell
            in zip(
                freevars,
                closure,
            )
        }


        self.assertIn(
            "orig_clean",
            closure_map,
        )


        real_clean = closure_map[
            "orig_clean"
        ]


        self.assertTrue(
            callable(real_clean)
        )


        real_source = inspect.getsource(
            real_clean
        )


        self.assertIn(
            "FACTURA_ESTADO_PAGADA_SYNC_BACKEND_V2",
            real_source,
        )

        self.assertIn(
            "factura_pagada_explicitamente",
            real_source,
        )

        self.assertNotIn(
            "FACTURA_ESTADO_PAGADA_SYNC_BACKEND_V1",
            real_source,
        )


    def test_detail_expone_cierre_real(
        self,
    ):
        source = inspect.getsource(
            views.factura_detail
        )

        self.assertIn(
            "FACTURA_PAGADA_EDITABLE_DETAIL_V2",
            source,
        )

        self.assertIn(
            "factura_cierre_real",
            source,
        )


    def test_anulacion_ignora_adjunto(
        self,
    ):
        source = inspect.getsource(
            views._gestion_factura_anulacion_blockers_v1
        )

        self.assertIn(
            '"adjuntos"',
            source,
        )

        self.assertIn(
            "factura_tiene_pago_real",
            source,
        )


    def test_template_usa_cierre_real(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "gestion"
            / "factura_detail.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "{% if factura_cierre_real %}",
            source,
        )

        self.assertIn(
            "FACTURA_PAGO_REAL_PROTEGIDA_UI_V3",
            source,
        )

        # Editar no debe estar en la lista CSS
        # de operaciones ocultadas por pago real.
        top = source[:2500]

        self.assertNotIn(
            'a[href*="/editar/"]',
            top,
        )


    def test_update_fuera_del_cierre(
        self,
    ):
        self.assertNotIn(
            "factura_update",
            factura_cierre.RUTAS_CERRADAS,
        )
