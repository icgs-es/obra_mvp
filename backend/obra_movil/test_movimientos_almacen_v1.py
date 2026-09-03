from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.test import override_settings
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.db import connection
from unittest.mock import patch
from types import SimpleNamespace
from django.template.loader import render_to_string
from django.urls import reverse

from actividad.models import ActividadPlataforma
from planificacion_obra.models import AlmacenObra, ObraPlanificacion, RecursoAlmacenMovimiento, RecursoCatalogo
from usuarios.models import Team

from .movimientos_almacen import (
    StockRecalculationError,
    classify_movement,
    delete_manual_movement,
    recalculate_resource_stock,
    update_manual_movement,
)


class MovimientosAlmacenV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.team = Team.objects.create(name="Movimientos V1")
        self.user = User.objects.create_user(username="mov-v1", password="x")
        self.team.members.add(self.user)
        for codename in ("change_recursoalmacenmovimiento", "delete_recursoalmacenmovimiento"):
            self.user.user_permissions.add(Permission.objects.get(codename=codename, content_type__app_label="planificacion_obra"))
        self.obra = ObraPlanificacion.objects.create(team=self.team, legacy_cod_obra=1, codigo="OB-1", nombre="Obra")
        self.almacen_a = AlmacenObra.objects.create(team=self.team, obra=self.obra, legacy_id_almacen="A", nombre="A")
        self.almacen_b = AlmacenObra.objects.create(team=self.team, obra=self.obra, legacy_id_almacen="B", nombre="B")
        self.recurso = RecursoCatalogo.objects.create(team=self.team, legacy_id=1, nombre="Material", stock=Decimal("12"), control_stock=True)

    def movement(self, **kwargs):
        defaults = dict(team=self.team, almacen=self.almacen_a, recurso=self.recurso, obra=self.obra,
                        legacy_id_movimiento=kwargs.pop("legacy_id_movimiento", 1), cantidad=Decimal("0"),
                        quedan=Decimal("0"), fecha_movimiento=date(2026, 1, 1), hora_movimiento=time(8),
                        tipo_movimiento="CONTROL_STOCK", raw_data={"origen": "obra_movil_almacen"})
        defaults.update(kwargs)
        return RecursoAlmacenMovimiento.objects.create(**defaults)

    def test_manual_recalculation_multiple_warehouses_and_edit_delete(self):
        self.movement(legacy_id_movimiento=1, quedan=Decimal("10"), cantidad=Decimal("10"))
        entry = self.movement(legacy_id_movimiento=2, tipo_movimiento="ENTRADA", cantidad=Decimal("5"), quedan=Decimal("15"), fecha_movimiento=date(2026, 1, 2))
        self.movement(legacy_id_movimiento=3, almacen=self.almacen_b, quedan=Decimal("2"), cantidad=Decimal("2"))
        recalculate_resource_stock(self.recurso.pk)
        with self.captureOnCommitCallbacks(execute=True):
            update_manual_movement(movement_id=entry.pk, user=self.user, values={"cantidad": Decimal("1"), "fecha_movimiento": date(2026, 1, 2), "hora_movimiento": time(8), "observaciones": "editado"})
        self.assertEqual(RecursoAlmacenMovimiento.objects.get(pk=entry.pk).quedan, Decimal("11.0000"))
        self.assertEqual(RecursoCatalogo.objects.get(pk=self.recurso.pk).stock, Decimal("13.0000"))
        with self.captureOnCommitCallbacks(execute=True):
            delete_manual_movement(movement_id=entry.pk, user=self.user)
        self.assertEqual(RecursoCatalogo.objects.get(pk=self.recurso.pk).stock, Decimal("12.0000"))
        self.assertGreaterEqual(ActividadPlataforma.objects.filter(modulo="obra_movil", accion__startswith="movimiento_almacen_").count(), 2)

    def test_documental_and_partida_origins_are_blocked(self):
        albaran = self.movement(legacy_id_movimiento=10, tipo_movimiento="ENTRADA", cod_albaran="A-1", raw_data={"source": "portal_gestion_albaran"})
        self.assertEqual(classify_movement(albaran), "ALBARAN")
        with self.assertRaises(PermissionError):
            delete_manual_movement(movement_id=albaran.pk, user=self.user)

    def test_negative_recalculation_rolls_back_edit(self):
        self.movement(legacy_id_movimiento=20, quedan=Decimal("1"), cantidad=Decimal("1"))
        entry = self.movement(legacy_id_movimiento=21, tipo_movimiento="SALIDA", cantidad=Decimal("1"), quedan=Decimal("0"), fecha_movimiento=date(2026, 1, 2))
        with self.assertRaises(StockRecalculationError):
            update_manual_movement(movement_id=entry.pk, user=self.user, values={"cantidad": Decimal("9"), "fecha_movimiento": date(2026, 1, 2), "hora_movimiento": time(8), "observaciones": ""})
        self.assertEqual(RecursoAlmacenMovimiento.objects.get(pk=entry.pk).cantidad, Decimal("1.0000"))

    def test_permission_is_required_even_for_manual(self):
        User = get_user_model()
        other = User.objects.create_user(username="mov-no-perm", password="x")
        self.team.members.add(other)
        movement = self.movement(legacy_id_movimiento=30, quedan=Decimal("0"))
        with self.assertRaises(PermissionError):
            update_manual_movement(movement_id=movement.pk, user=other, values={"cantidad": Decimal("1"), "fecha_movimiento": date(2026, 1, 1), "hora_movimiento": time(8), "observaciones": ""})

    def test_listing_uses_single_exists_for_real_links(self):
        import inspect
        from .views import almacen_movimientos, _alm_ux3_apply_team_scope
        source = inspect.getsource(almacen_movimientos)
        self.assertIn("Exists", source)
        self.assertIn("select_related", source)
        self.assertIn("select_for_update", inspect.getsource(__import__("obra_movil.movimientos_almacen", fromlist=["recalculate_resource_stock"]).recalculate_resource_stock))
        self.movement(legacy_id_movimiento=40, quedan=Decimal("0"))
        request = type("Request", (), {"user": self.user, "session": {}})()
        self.assertTrue(_alm_ux3_apply_team_scope(RecursoAlmacenMovimiento.objects.all(), request).filter(team=self.team).exists())

    @override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
    def test_listing_render_actions_layout_and_filters(self):
        manual = self.movement(legacy_id_movimiento=8740, quedan=Decimal("4"))
        blocked = self.movement(legacy_id_movimiento=9025, cod_albaran="ALB-1", raw_data={"source": "portal_gestion_albaran"})
        for mov in (manual, blocked):
            mov.ux3_destino_label = "Almacén"
            mov.ux3_pendiente_persona = False
            mov.origin_code = classify_movement(mov)
            mov.origin_label = "Manual" if mov.origin_code == "MANUAL" else "Desde albarán"
            mov.can_edit = mov is manual
            mov.can_delete = mov is manual
            mov.blocked_reason = "" if mov is manual else "Bloqueado: Desde albarán."
        html = render_to_string("obra_movil/almacen_movimientos.html", {
            "movimientos": [manual, blocked], "total": 2, "pendientes_count": 0,
            "filtros": {"q": "", "tipo": "", "estado": "", "destino": "", "empleado": "", "almacen": "", "obra": "", "fecha_desde": "", "fecha_hasta": ""},
            "empleados": [], "almacenes": [], "obras": [], "tipos": ["ENTRADA", "SALIDA"],
            "page_obj": SimpleNamespace(has_other_pages=False),
        }, request=RequestFactory().get("/app/obra-movil/almacen/movimientos/"))
        self.assertIn("Editar", html)
        self.assertIn("Eliminar", html)
        self.assertIn(reverse("obra_movil:almacen_movimiento_editar", args=[manual.pk]), html)
        self.assertIn(reverse("obra_movil:almacen_movimiento_eliminar", args=[manual.pk]), html)
        self.assertNotIn(reverse("obra_movil:almacen_movimiento_editar", args=[blocked.pk]), html)
        self.assertNotIn(reverse("obra_movil:almacen_movimiento_eliminar", args=[blocked.pk]), html)
        headers = ["ID", "Fecha/hora", "Tipo", "Recurso", "Cant.", "Quedan", "Destino", "Albarán", "Obs.", "Estado", "Acciones"]
        positions = [html.index(f"<th>{header}</th>") for header in headers]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Bloqueado: Desde albarán.", html.split('title="Bloqueado: Desde albarán."', 1)[0])
        self.assertIn('title="Bloqueado: Desde albarán."', html)
        self.assertIn('class="alm3-obs"', html)
        self.assertNotIn("<th>Almacén</th>", html)
        self.assertNotIn("<th>Persona</th>", html)
        self.assertIn('name="almacen"', html)
        self.assertIn('name="empleado"', html)
