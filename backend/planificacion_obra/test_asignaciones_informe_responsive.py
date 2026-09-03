from datetime import date
from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.template import Context, Engine
from django.test import RequestFactory, SimpleTestCase


class AsignacionesInformeResponsiveTests(SimpleTestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_path = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "planificacion_obra"
            / "asignaciones_informe.html"
        )
        cls.css_path = cls.template_path.with_name("_responsive_productividad.css")
        cls.source = cls.template_path.read_text(encoding="utf-8")
        cls.css = cls.css_path.read_text(encoding="utf-8")
        cls.engine = Engine(
            dirs=[str(cls.template_path.parents[1]), str(settings.BASE_DIR / "templates")],
            app_dirs=True,
            libraries={"static": "django.templatetags.static"},
        )

    def _render(self, context):
        return self.engine.get_template(
            "planificacion_obra/asignaciones_informe.html"
        ).render(Context(context))

    def _context(self, *, rows=None, query=""):
        request = RequestFactory().get(
            "/app/planificacion-obra/asignaciones/informe/" + query
        )
        request.user = AnonymousUser()
        return {
            "request": request,
            "rows": [] if rows is None else rows,
            "fecha_desde": date(2026, 8, 1),
            "fecha_hasta": date(2026, 8, 31),
            "total_asignaciones": 1,
            "total_empleados": 1,
            "total_viviendas": 1,
            "total_horas": "8,00",
            "total_importe_display": "1.234,56 €",
            "filtros_linea_superior_v14": "Periodo: 01/08/2026–31/08/2026",
            "filters": {},
            "querystring": "",
            "obras": [],
            "edificios": [],
            "viviendas": [],
            "plantas": [],
            "capitulos": [],
            "partidas": [],
            "empleados": [],
            "estados": [],
        }

    def test_filter_and_navigation_contract_is_preserved(self):
        for name in (
            "desde", "hasta", "obra", "edificio", "vivienda", "planta",
            "capitulo", "partida", "empleado", "estado",
        ):
            self.assertIn(f'name="{name}"', self.source)
        for element_id in (
            "report-filter-obra", "report-filter-edificio",
            "report-filter-vivienda", "report-filter-planta",
            "report-filter-capitulo", "report-filter-partida",
        ):
            self.assertIn(f'id="{element_id}"', self.source)
        self.assertIn("/app/planificacion-obra/asignaciones/calendario/filtros/", self.source)
        self.assertIn("planificacion_obra:asignaciones_gantt", self.source)
        self.assertIn("planificacion_obra:asignaciones_calendario", self.source)
        self.assertIn("window.print()", self.source)

    def test_mobile_filter_kpis_cards_and_touch_targets(self):
        self.assertIn("asignaciones-report-filter-disclosure mb-3\" open", self.source)
        self.assertNotIn('data-bs-toggle="collapse"', self.source)
        self.assertNotIn("asignaciones-report-filters collapse", self.source)
        self.assertIn("asignaciones-report-period", self.source)
        self.assertIn("@media screen and (max-width: 767px)", self.css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", self.css)
        self.assertIn(".asignaciones-report-kpi-total", self.css)
        self.assertIn("min-height: 44px", self.css)
        self.assertIn('class="asignaciones-report-mobile-cards"', self.source)
        self.assertIn(".asignaciones-report-table-wrap", self.css)
        for field in (
            "row.fecha", "row.empleado", "row.obra", "row.edificio",
            "row.vivienda", "row.planta", "row.capitulo_display",
            "row.trabajo_display", "row.estado", "row.horas_display",
            "row.importe_display",
        ):
            self.assertGreaterEqual(self.source.count(field), 2, field)

    def test_tablet_desktop_print_and_widget_scope(self):
        self.assertIn("(min-width: 768px) and (max-width: 991px)", self.css)
        self.assertIn("(min-width: 992px) and (max-width: 1199px)", self.css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", self.css)
        self.assertIn("min-width: 1100px", self.css)
        self.assertIn("@media screen and (min-width: 1200px)", self.css)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", self.css)
        self.assertIn("@media print", self.css)
        self.assertIn("display: block !important", self.css)
        self.assertIn("body.asignaciones-report-active #intasa-help-launcher", self.css)
        self.assertIn("body.asignaciones-report-active #intasa-correo-dock-launcher", self.css)
        self.assertIn('classList.add("asignaciones-report-active")', self.source)
        self.assertNotIn("|safe", self.source)

    def test_template_renders_same_row_in_table_and_mobile_card_without_queries(self):
        row = {
            "fecha": date(2026, 8, 24),
            "empleado": "Empleado Responsive",
            "obra": "Obra Norte",
            "edificio": "Fase A",
            "vivienda": "V-12",
            "planta": "P2",
            "capitulo_display": "Capítulo largo",
            "trabajo_display": "Trabajo completo",
            "estado": "Planificada",
            "horas_display": "8,00",
            "importe_display": "1.234,56 €",
        }
        html = self._render(self._context(rows=[row]))
        self.assertGreaterEqual(html.count("Empleado Responsive"), 2)
        for value in row.values():
            if not isinstance(value, date):
                self.assertIn(str(value), html)
        self.assertIn("asignaciones-report-mobile-cards", html)

    def test_empty_state_and_active_filter_render(self):
        html = self._render(self._context(query="?obra=1"))
        self.assertIn(
            "No hay asignaciones para el periodo y filtros seleccionados.", html
        )
        self.assertIn("Activos", html)
        self.assertIn("asignaciones-report-filter-disclosure mb-3\" open", html)
