import inspect
from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion import views


class FacturaLineaAutocompleteV2Tests(SimpleTestCase):
    def test_endpoint_exposes_high_limit_and_more_signal(self):
        source = inspect.getsource(views.articulos_compra_search)
        self.assertIn('request.GET.get("limit", "200")', source)
        self.assertIn('"has_more"', source)
        self.assertIn('normalizar_clave_articulo(q)', source)
        self.assertIn('alias.codigo_proveedor', source)

    def test_ui_never_silently_slices_and_supports_keyboard(self):
        template = (Path(__file__).resolve().parents[2] / "templates" / "gestion" / "factura_linea_form.html").read_text()
        self.assertNotIn("items.slice(0, 12)", template)
        self.assertIn("max-height: 22rem", template)
        self.assertIn('event.key === "ArrowDown"', template)
        self.assertIn('event.key === "Enter"', template)
        self.assertIn("Hay más resultados", template)
