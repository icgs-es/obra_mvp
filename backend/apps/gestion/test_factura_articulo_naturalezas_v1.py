
from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion.unit_catalog_v1 import (
    normalize_nature,
)


class FacturaArticuloNaturalezasV1Tests(
    SimpleTestCase
):

    def test_canonical(self):

        cases = {
            "MATERIAL": "MATERIAL",
            "SERVICIO": "SERVICIO",
            "HERRAMIENTA": "HERRAMIENTA",
            "MAQUINARIA": "MAQUINARIA",
            "PORTES": "PORTES",
        }

        for raw, expected in cases.items():
            self.assertEqual(
                normalize_nature(raw),
                expected,
            )


    def test_aliases(self):

        cases = {
            "MATERIALES": "MATERIAL",
            "SERVICIOS": "SERVICIO",
            "HERRAMIENTAS": "HERRAMIENTA",
            "MAQUINARIAS": "MAQUINARIA",
            "PORTE": "PORTES",
        }

        for raw, expected in cases.items():
            self.assertEqual(
                normalize_nature(raw),
                expected,
            )


    def test_unknown_preserves_default(self):

        self.assertEqual(
            normalize_nature(
                "OTRO",
                default="E.P.I.S.",
            ),
            "E.P.I.S.",
        )


    def test_modal_options(self):

        text = Path(
            "templates/gestion/"
            "_unidad_compra_v1a_js.html"
        ).read_text()

        expected = {
            "MATERIAL": "Material",
            "SERVICIO": "Servicio",
            "HERRAMIENTA": "Herramienta",
            "MAQUINARIA": "Maquinaria",
            "PORTES": "Portes",
        }

        for value, label in expected.items():

            self.assertIn(
                f'value="{value}"',
                text,
            )

            self.assertIn(
                label,
                text,
            )

