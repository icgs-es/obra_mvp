from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


class FacturaLineasLegiblesV1Tests(
    SimpleTestCase
):
    def setUp(self):
        self.path = Path(
            "templates/gestion/"
            "factura_detail.html"
        )
        self.text = self.path.read_text()

    def test_template_carga(self):
        template = get_template(
            "gestion/factura_detail.html"
        )
        self.assertIsNotNone(template)

    def test_parche_unico(self):
        self.assertEqual(
            self.text.count(
                "FACTURA_LINEAS_LEGIBLES_V1"
            ),
            1,
        )

    def test_codigo_permite_salto(self):
        self.assertIn(
            "overflow-wrap: anywhere",
            self.text,
        )
        self.assertIn(
            "word-break: break-word",
            self.text,
        )

    def test_descripcion_no_invade_columnas(self):
        self.assertIn(
            "width: 365px",
            self.text,
        )
        self.assertIn(
            "overflow: hidden",
            self.text,
        )

    def test_tabla_tiene_scroll_seguro(self):
        self.assertIn(
            "overflow-x: auto",
            self.text,
        )
        self.assertIn(
            "min-width: 1180px",
            self.text,
        )
