from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from usuarios.models import Team
from apps.gestion.models import (
    AlbaranProveedorGestion, AlbaranProveedorLineaGestion, ArticuloCompra,
    FacturaAlbaranGestion, FacturaProveedorGestion, FacturaProveedorLineaGestion,
)
from planificacion_obra.materiales_asignados import build_materiales_report, csv_safe
from planificacion_obra.models import ObraPlanificacion, RecursoCatalogo, TareaRecursoReal


class MaterialesAsignadosV1Tests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Materiales V1")
        self.obra = ObraPlanificacion.objects.create(team=self.team, legacy_cod_obra=3, codigo="3", nombre="OBRA COMPETA")
        self.recurso = RecursoCatalogo.objects.create(team=self.team, legacy_id=167, nombre="GASOIL", tipo="MATERIAL", unidad="L")

    def real(self, **kwargs):
        data = dict(team=self.team, legacy_id_recurso_tarea=1, legacy_cod_obra=3,
                    recurso=self.recurso, legacy_tipo_recurso="MATERIAL", cantidad=Decimal("40"),
                    unidad="L", precio_unidad=Decimal("2"), costo_recurso_real=Decimal("80"),
                    inicio_recurso_real=date(2026, 6, 30))
        data.update(kwargs)
        return TareaRecursoReal.objects.create(**data)

    def test_empty_obra(self):
        report = build_materiales_report(self.obra)
        self.assertEqual(report["totals"]["assignments"], 0)

    def test_real_assignment_is_one_economic_row(self):
        self.real()
        report = build_materiales_report(self.obra)
        self.assertEqual(report["totals"]["assignments"], 1)
        self.assertEqual(report["summary"][0]["quantity"], Decimal("40"))
        self.assertEqual(report["totals"]["base"], Decimal("80.00"))

    def test_labour_without_catalog_resource_is_excluded(self):
        TareaRecursoReal.objects.create(team=self.team, legacy_id_recurso_tarea=2,
            legacy_cod_obra=3, legacy_tipo_recurso="M.O. ADM.", cantidad=8, unidad="HRS")
        self.assertEqual(build_materiales_report(self.obra)["totals"]["assignments"], 0)

    def test_linked_invoice_does_not_duplicate_albaran_assignment(self):
        art = ArticuloCompra.objects.create(team=self.team, nombre="Gasoil", recurso_catalogo_id=self.recurso.pk)
        alb = AlbaranProveedorGestion.objects.create(team=self.team, cod_albaran="A-1", obra_planificacion=self.obra)
        AlbaranProveedorLineaGestion.objects.create(albaran=alb, linea=1, articulo_compra=art,
            cantidad=100, precio_unitario=2, importe_linea=200)
        fac = FacturaProveedorGestion.objects.create(team=self.team, cod_factura="F-1", obra_planificacion=self.obra,
            importe_base_imponible=200, importe_iva=42, importe_factura=242)
        FacturaAlbaranGestion.objects.create(team=self.team, factura=fac, albaran=alb, importe_asignado=242)
        FacturaProveedorLineaGestion.objects.create(factura=fac, albaran=alb, linea=1,
            linea_albaran_legacy=1, articulo_compra=art, cantidad=100, precio_unitario=2, importe_linea=200)
        self.real(cod_albaran="A-1", num_linea_albaran=1)
        report = build_materiales_report(self.obra)
        self.assertEqual(report["totals"]["assignments"], 1)
        row = report["details"][0]
        self.assertEqual(row["origin"], "ALBARÁN")
        self.assertEqual(row["valuation_source"], "FACTURA")
        self.assertEqual(row["base"], Decimal("80.00"))
        self.assertEqual(row["iva"], Decimal("16.80"))

    def test_document_net_base_does_not_apply_discount_twice(self):
        art = ArticuloCompra.objects.create(team=self.team, nombre="Gasoil", recurso_catalogo_id=self.recurso.pk)
        alb = AlbaranProveedorGestion.objects.create(team=self.team, cod_albaran="A-NET", obra_planificacion=self.obra)
        AlbaranProveedorLineaGestion.objects.create(
            albaran=alb, linea=1, articulo_compra=art, cantidad=100,
            precio_unitario=2, importe_descuento=20, importe_linea=180,
        )
        self.real(cod_albaran="A-NET", num_linea_albaran=1)
        row = build_materiales_report(self.obra)["details"][0]
        self.assertEqual(row["price"], Decimal("1.8"))
        self.assertEqual(row["net_total"], Decimal("72.00"))

    def test_csv_injection_is_neutralized(self):
        for value in ("=1+1", "+cmd", "-2", "@x"):
            self.assertTrue(csv_safe(value).startswith("'"))

    def test_functional_permission_team_scope_and_economic_redaction(self):
        user = get_user_model().objects.create_user(username="materials-user")
        self.team.members.add(user)
        user.user_permissions.add(Permission.objects.get(codename="view_tarearecursoreal"))
        self.real()
        self.client.force_login(user)
        response = self.client.get(reverse("planificacion_obra:materiales_asignados"), {"obra": self.obra.pk}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Precio unitario histórico")
        self.assertNotContains(response, "Total neto asignado")

    def test_is_staff_without_permission_is_forbidden(self):
        user = get_user_model().objects.create_user(username="materials-staff", is_staff=True)
        self.team.members.add(user)
        self.client.force_login(user)
        response = self.client.get(reverse("planificacion_obra:materiales_asignados"), {"obra": self.obra.pk}, secure=True)
        self.assertEqual(response.status_code, 403)

    def test_other_team_is_not_found(self):
        user = get_user_model().objects.create_user(username="materials-outsider")
        user.user_permissions.add(Permission.objects.get(codename="view_tarearecursoreal"))
        self.client.force_login(user)
        response = self.client.get(reverse("planificacion_obra:materiales_asignados"), {"obra": self.obra.pk}, secure=True)
        self.assertEqual(response.status_code, 404)

    def test_superuser_bypass(self):
        user = get_user_model().objects.create_superuser(username="materials-root", email="root@example.invalid", password="x")
        self.client.force_login(user)
        response = self.client.get(reverse("planificacion_obra:materiales_asignados"), {"obra": self.obra.pk}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total neto asignado")
