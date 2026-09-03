from pathlib import Path

from django.test import SimpleTestCase


class AsignacionesInformeFilterHotfixTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "planificacion_obra"
            / "asignaciones_informe.html"
        )
        cls.html = template.read_text(encoding="utf-8")
        cls.css = template.with_name("_responsive_productividad.css").read_text(
            encoding="utf-8"
        )

    def test_all_filter_fields_and_get_contract_are_preserved(self):
        names = (
            "desde", "hasta", "obra", "edificio", "vivienda", "planta",
            "capitulo", "partida", "empleado", "estado",
        )
        for name in names:
            self.assertEqual(self.html.count(f'name="{name}"'), 1, name)

        ids = (
            "report-filter-obra", "report-filter-edificio",
            "report-filter-vivienda", "report-filter-planta",
            "report-filter-capitulo", "report-filter-partida",
        )
        for element_id in ids:
            self.assertEqual(self.html.count(f'id="{element_id}"'), 1, element_id)

    def test_progressive_disclosure_is_open_without_javascript(self):
        self.assertIn(
            '<details class="asignaciones-report-filter-disclosure mb-3" open>',
            self.html,
        )
        self.assertIn("<summary", self.html)
        self.assertNotIn('data-bs-toggle="collapse"', self.html)
        self.assertNotIn('data-bs-target="#asignacionesReportFilters"', self.html)
        form_tag = self.html.split('<form id="pi-report-filter-form"', 1)[1].split(">", 1)[0]
        self.assertNotIn("collapse", form_tag)
        self.assertNotIn("display: none", form_tag)

    def test_submit_and_clear_actions_remain_in_the_correct_form(self):
        form = self.html.split('<form id="pi-report-filter-form"', 1)[1].split(
            "</form>", 1
        )[0]
        self.assertIn('method="get"', self.html)
        self.assertIn('type="submit" class="btn btn-primary">Filtrar</button>', form)
        self.assertIn("planificacion_obra:asignaciones_informe", form)
        self.assertIn(">Limpiar</a>", form)

    def test_dependent_select_javascript_and_navigation_are_unchanged(self):
        self.assertIn(
            "/app/planificacion-obra/asignaciones/calendario/filtros/", self.html
        )
        for element_id in (
            "report-filter-obra", "report-filter-edificio",
            "report-filter-vivienda", "report-filter-planta",
            "report-filter-capitulo", "report-filter-partida",
        ):
            self.assertGreaterEqual(self.html.count(element_id), 2, element_id)
        self.assertIn("planificacion_obra:asignaciones_gantt", self.html)
        self.assertIn("planificacion_obra:asignaciones_calendario", self.html)

    def test_mobile_desktop_print_and_widgets_are_scoped(self):
        self.assertIn(".asignaciones-report-filters .row > [class*=\"col-\"]", self.css)
        self.assertIn(".asignaciones-report-filters .btn", self.css)
        self.assertIn("@media screen and (min-width: 768px)", self.css)
        self.assertIn("@media print", self.css)
        self.assertIn("body.asignaciones-report-active #intasa-help-launcher", self.css)
        self.assertIn(
            "body.asignaciones-report-active #intasa-correo-dock-launcher", self.css
        )
