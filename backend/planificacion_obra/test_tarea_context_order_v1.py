from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TareaContextOrderV1Tests(
    SimpleTestCase
):
    def test_dos_botones_transmiten_contexto(
        self,
    ):
        source = (
            Path(settings.BASE_DIR)
            / "templates"
            / "planificacion_obra"
            / "planning_list.html"
        ).read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            source.count(
                "PLANNING_NEW_TASK_"
                "CONTEXT_WITH_OBRA_V1"
            ),
            1,
        )

        self.assertEqual(
            source.count(
                "PLANNING_NEW_TASK_"
                "CONTEXT_WITHOUT_OBRA_V1"
            ),
            1,
        )

        for value in (
            "request.get_full_path|urlencode",
            "filtros.fase|urlencode",
            "filtros.vivienda|urlencode",
            "filtros.planta|urlencode",
            "filtros.capitulo|urlencode",
        ):
            self.assertIn(
                value,
                source,
            )

    def test_formulario_precarga_contexto(
        self,
    ):
        source = (
            Path(settings.BASE_DIR)
            / "planificacion_obra"
            / "views.py"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "PLANNING_NEW_TASK_"
                "CONTEXT_INITIAL_V1"
            ),
            source,
        )

        self.assertIn(
            'initial["partida"] = None',
            source,
        )

        self.assertIn(
            '"unidad_obra"',
            source,
        )

        self.assertIn(
            '"legacy_planta"',
            source,
        )

        self.assertIn(
            '"capitulo"',
            source,
        )

    def test_orden_por_vivienda_y_planta(
        self,
    ):
        source = (
            Path(settings.BASE_DIR)
            / "planificacion_obra"
            / "views.py"
        ).read_text(
            encoding="utf-8"
        )

        start = source.index(
            "def tarea_manual_create("
        )

        end = source.index(
            "\ndef ",
            start + 10,
        )

        function_source = source[
            start:end
        ]

        self.assertIn(
            "PLANNING_TASK_ORDER_SCOPE_V1",
            function_source,
        )

        self.assertIn(
            "legacy_cod_fase=",
            function_source,
        )

        self.assertIn(
            "legacy_cod_vivienda=",
            function_source,
        )

        self.assertIn(
            "legacy_planta__iexact=",
            function_source,
        )

        self.assertIn(
            "select_for_update",
            function_source,
        )

        self.assertNotIn(
            (
                ".filter(team=tarea.team, "
                "obra=obra)"
            ),
            function_source,
        )

    def test_formulario_conserva_retorno(
        self,
    ):
        source = (
            Path(settings.BASE_DIR)
            / "templates"
            / "planificacion_obra"
            / "tarea_form.html"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "PLANNING_TASK_FORM_NEXT_V1",
            source,
        )

        self.assertIn(
            'name="next"',
            source,
        )
