from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from usuarios.models import Team
from .models import AlmacenObra, ObraPlanificacion, RecursoAlmacenMovimiento, RecursoCatalogo


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class PlanningMovimientosNavigationV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.team = Team.objects.create(name="Planning Movimientos")
        self.user = User.objects.create_user(username="planning-mov", password="x")
        self.team.members.add(self.user)
        self.obra = ObraPlanificacion.objects.create(team=self.team, legacy_cod_obra=1, codigo="P-1", nombre="Obra")
        self.almacen = AlmacenObra.objects.create(team=self.team, obra=self.obra, nombre="Almacén")
        self.recurso = RecursoCatalogo.objects.create(team=self.team, legacy_id=167, nombre="Gasoil")
        self.mov = RecursoAlmacenMovimiento.objects.create(
            team=self.team, obra=self.obra, almacen=self.almacen, recurso=self.recurso,
            legacy_id_movimiento=1, cantidad=Decimal("2"), unidad="L", quedan=Decimal("2"),
            fecha_movimiento=date(2026, 8, 31), hora_movimiento=time(10),
            tipo_movimiento="SALIDA", raw_data={"origen": "obra_movil_gasoil"},
        )

    @override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
    def test_planning_template_contract(self):
        self.mov.origin_label = "Manual"
        self.mov.tiene_real = False
        html = render_to_string("planificacion_obra/almacen_movimientos.html", {
            "page_obj": [self.mov], "total": 818, "estado": "pendiente_partida",
            "q": "", "tipo": "", "almacen_id": "", "obra_id": "", "fecha_desde": "", "fecha_hasta": "",
            "almacenes": [], "obras": [], "tipos": ["SALIDA"], "querystring": "", "can_imputar": True,
        }, request=RequestFactory().get("/app/planificacion-obra/almacen/movimientos/"))
        headers = ["ID", "Fecha/hora", "Tipo", "Almacén", "Recurso", "Cantidad", "Destino", "Origen", "Estado", "Acciones"]
        positions = [html.index(f"<th>{h}</th>") if h not in {"Cantidad", "Acciones"} else html.index(f"{h}</th>") for h in headers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Pendientes de almacén", html)
        self.assertIn("818 movimientos pendientes", html)
        self.assertIn("31/08/2026", html)
        self.assertIn("10:00", html)
        self.assertIn("Manual", html)
        self.assertIn('name="almacen"', html)
        self.assertNotIn("Origen doc.", html)

    def test_imputar_requires_add_real_permission_and_team_scope(self):
        url = reverse("planificacion_obra:almacen_movimiento_imputar_partida", args=[self.mov.pk])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url, follow=True).status_code, 403)
        perm = Permission.objects.get(codename="add_tarearecursoreal", content_type__app_label="planificacion_obra")
        self.user.user_permissions.add(perm)
        self.assertEqual(self.client.get(url, follow=True).status_code, 200)
        outsider = get_user_model().objects.create_user(username="outsider", password="x")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url, follow=True).status_code, 404)

    def test_urls_and_navigation_anchors(self):
        self.assertEqual(reverse("obra_movil:almacen_movimientos"), "/app/obra-movil/almacen/movimientos/")
        self.assertEqual(reverse("planificacion_obra:almacen_movimientos_list"), "/app/planificacion-obra/almacen/movimientos/")
        self.assertEqual(reverse("planificacion_obra:almacen_movimientos_general"), "/app/planificacion-obra/almacen/movimientos/general/")

    def test_general_template_is_distinct_and_has_manual_actions(self):
        self.mov.origin_label = "Manual"
        self.mov.origin_code = "MANUAL"
        self.mov.can_edit = True
        self.mov.can_delete = True
        html = render_to_string("planificacion_obra/almacen_movimientos.html", {
            "page_obj": [self.mov], "total": 1, "estado": "", "general_mode": True,
            "q": "", "tipo": "", "almacen_id": "", "obra_id": "", "fecha_desde": "", "fecha_hasta": "",
            "almacenes": [], "obras": [], "tipos": ["SALIDA"], "querystring": "", "can_imputar": False,
        }, request=RequestFactory().get("/app/planificacion-obra/almacen/movimientos/general/"))
        self.assertIn("Movimientos de almacén", html)
        self.assertIn("Editar", html)
        self.assertIn("Eliminar", html)
        self.assertNotIn("Pendientes de enviar a partida", html)

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_old_mobile_route_redirects_to_desktop_alias(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("obra_movil:almacen_movimientos"), follow=False)
        self.assertIn(response.status_code, (301, 302))
        self.assertTrue(response["Location"].endswith(reverse("planificacion_obra:almacen_movimientos_general")), response["Location"])

    def test_mobile_index_and_section_do_not_expose_history_card(self):
        index_html = render_to_string("obra_movil/index.html", {})
        section_html = render_to_string("obra_movil/section.html", {
            "section_key": "almacen", "section_title": "Almacén", "section_subtitle": "",
            "section_icon": "bi-box-seam", "primary_url": "", "secondary_url": "",
        })
        self.assertNotIn("Listado general, filtros y trazabilidad", index_html)
        self.assertNotIn("href=\"/app/obra-movil/almacen/movimientos/\"", section_html)
        self.assertIn("Almacén", index_html)
        self.assertIn("Stock", index_html)
        self.assertIn("Mortero", index_html)
