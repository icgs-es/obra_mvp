from pathlib import Path

from django.conf import settings
from django.template.loader import (
    get_template,
)
from django.test import SimpleTestCase


class FloatingDockPolishTests(
    SimpleTestCase
):
    def test_dock_contains_drag_support(
        self,
    ):
        get_template(
            "correo/_floating_dock.html"
        )

        path = (
            Path(settings.BASE_DIR)
            / "correo"
            / "templates"
            / "correo"
            / "_floating_dock.html"
        )

        text = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "INTASA_CORREO_V1F3_DRAGGABLE_DOCK",
            text,
        )

        self.assertIn(
            "setPointerCapture",
            text,
        )

        self.assertIn(
            "intasaCorreoDockPositionV1",
            text,
        )

        self.assertIn(
            "viewportPosition",
            text,
        )

    def test_intasa_ia_is_after_obra(
        self,
    ):
        get_template(
            "base.html"
        )

        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "base.html"
        )

        text = path.read_text(
            encoding="utf-8"
        )

        obra_position = text.index(
            'id="navObra"'
        )

        ia_position = text.index(
            "INTASA_IA_NAV_DIFFERENTIAL_V1"
        )

        self.assertGreater(
            ia_position,
            obra_position,
        )

        self.assertIn(
            "intasa-ia-nav-divider",
            text,
        )

        self.assertIn(
            "intasa-ia-nav-link",
            text,
        )

        self.assertNotIn(
            "NAV_INTASA_IA_V1A",
            text,
        )
