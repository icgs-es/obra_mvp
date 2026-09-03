import csv
import io
import re
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from usuarios.models import Team
from planificacion_obra.materiales_asignados import build_materiales_report
from planificacion_obra.models import (
    ObraPlanificacion,
    RecursoAlmacenMovimiento,
    RecursoCatalogo,
    TareaRecursoPrevisto,
    TareaRecursoReal,
)


class MaterialesAsignadosLayoutPrintV2Tests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Materiales operativos V2")
        self.obra = ObraPlanificacion.objects.create(
            team=self.team,
            legacy_cod_obra=3,
            codigo="3",
            nombre="OBRA COMPETA",
        )
        self.resource = RecursoCatalogo.objects.create(
            team=self.team,
            legacy_id=167,
            nombre="GASOIL",
            tipo="MATERIAL",
            unidad="L",
        )
        self.root = get_user_model().objects.create_superuser(
            username="materials-v2-root",
            email="materials-v2@example.invalid",
            password="x",
        )
        self.client.force_login(self.root)

    def real(self, index=1, **changes):
        values = {
            "team": self.team,
            "legacy_id_recurso_tarea": index,
            "legacy_cod_obra": 3,
            "legacy_cod_vivienda": "13",
            "legacy_planta": "INTERIOR",
            "legacy_capitulo": "C05",
            "legacy_partida": "05.029",
            "recurso": self.resource,
            "legacy_tipo_recurso": "MATERIAL",
            "cantidad": Decimal("18.1250"),
            "unidad": "L",
            "precio_unidad": Decimal("90.0000"),
            "costo_recurso_real": Decimal("1631.2500"),
            "inicio_recurso_real": date(2026, 6, 30),
        }
        values.update(changes)
        return TareaRecursoReal.objects.create(**values)

    @staticmethod
    def detail_table(content):
        match = re.search(r'<table id="materials-detail-table".*?</table>', content, re.S)
        if not match:
            raise AssertionError("No se renderizó la tabla operativa")
        return match.group(0)

    def test_service_uses_only_real_assignments_and_keeps_internal_precision(self):
        self.real()
        TareaRecursoPrevisto.objects.create(
            team=self.team,
            legacy_row_number=1,
            legacy_cod_obra=3,
            recurso=self.resource,
            cantidad=Decimal("999.0000"),
            unidad="L",
        )
        RecursoAlmacenMovimiento.objects.create(
            team=self.team,
            legacy_id_movimiento=987654,
            recurso=self.resource,
            legacy_cod_obra=3,
            cantidad=Decimal("500.0000"),
        )
        report = build_materiales_report(self.obra)
        self.assertEqual(report["totals"]["assignments"], 1)
        self.assertEqual(report["details"][0]["quantity"], Decimal("18.1250"))
        self.assertEqual(report["details"][0]["quantity_display"], "18,1")

    def test_price_and_total_are_historical_net_without_vat(self):
        self.real(cantidad=Decimal("18.0000"), precio_unidad=Decimal("90.0000"))
        item = build_materiales_report(self.obra)["details"][0]
        self.assertEqual(item["price"], Decimal("90.0000"))
        self.assertEqual(item["net_total"], Decimal("1620.00"))
        self.assertEqual(item["price_display"], "90,00 €")
        self.assertEqual(item["net_total_display"], "1.620,00 €")

    def test_operational_table_has_exact_columns_and_full_destination(self):
        self.real()
        response = self.client.get(
            reverse("planificacion_obra:materiales_asignados"),
            {"obra": self.obra.pk},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        table = self.detail_table(response.content.decode())
        headers = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table, re.S)
        self.assertEqual(headers, [
            "Fecha", "Código", "Artículo", "Cantidad", "Unidad",
            "Precio", "Total", "Origen", "Proveedor", "Destino",
        ])
        self.assertNotIn(">Base<", table)
        self.assertNotIn(">IVA<", table)
        self.assertNotIn(">Valoración<", table)
        self.assertIn("Vivienda 13 · INTERIOR · C05 · 05.029", table)
        self.assertIn('title="Vivienda 13 · INTERIOR · C05 · 05.029"', table)

    def test_screen_is_paginated_but_print_contains_all_filtered_rows(self):
        TareaRecursoReal.objects.bulk_create([
            TareaRecursoReal(
                team=self.team,
                legacy_id_recurso_tarea=index,
                legacy_cod_obra=3,
                recurso=self.resource,
                legacy_tipo_recurso="MATERIAL",
                cantidad=Decimal("1.0000"),
                unidad="L",
                precio_unidad=Decimal("2.0000"),
                inicio_recurso_real=date(2026, 6, 30),
            )
            for index in range(1, 106)
        ])
        self.real(index=106, inicio_recurso_real=date(2025, 12, 31))
        params = {"obra": self.obra.pk, "desde": "2026-01-01", "hasta": "2026-12-31"}
        screen = self.client.get(reverse("planificacion_obra:materiales_asignados"), params, secure=True)
        printed = self.client.get(reverse("planificacion_obra:materiales_asignados_print"), params, secure=True)
        exported = self.client.get(reverse("planificacion_obra:materiales_asignados_csv"), params, secure=True)
        self.assertEqual(screen.content.count(b'class="materials-screen-row"'), 100)
        self.assertEqual(printed.content.count(b'class="materials-print-row"'), 105)
        self.assertContains(printed, "Asignaciones reales</div>105")
        csv_rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(csv_rows) - 1, 105)

    def test_print_contract_is_landscape_complete_and_not_ellipsized(self):
        self.real()
        response = self.client.get(
            reverse("planificacion_obra:materiales_asignados_print"),
            {"obra": self.obra.pk},
            secure=True,
        )
        html = response.content.decode()
        self.assertIn("@page { size: A4 landscape;", html)
        self.assertIn("thead { display: table-header-group; }", html)
        self.assertIn("page-break-inside: avoid", html)
        self.assertNotIn("text-overflow: ellipsis", html)
        self.assertIn("Vivienda 13 · INTERIOR · C05 · 05.029", html)

    def test_csv_uses_operational_net_columns_and_canonical_precision(self):
        self.real()
        response = self.client.get(
            reverse("planificacion_obra:materiales_asignados_csv"),
            {"obra": self.obra.pk},
            secure=True,
        )
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0][:10], [
            "Fecha", "Código", "Artículo", "Cantidad", "Unidad",
            "Precio unitario histórico", "Total neto asignado", "Origen", "Proveedor", "Destino",
        ])
        self.assertNotIn("Base", rows[0])
        self.assertNotIn("IVA", rows[0])
        self.assertEqual(Decimal(rows[1][3]), Decimal("18.1250"))
        self.assertEqual(Decimal(rows[1][6]), Decimal("1631.25"))

    def test_no_economic_permission_redacts_screen_print_and_csv(self):
        user = get_user_model().objects.create_user(username="materials-v2-no-money")
        self.team.members.add(user)
        user.user_permissions.add(Permission.objects.get(codename="view_tarearecursoreal"))
        self.real()
        self.client.force_login(user)
        params = {"obra": self.obra.pk}
        screen = self.client.get(reverse("planificacion_obra:materiales_asignados"), params, secure=True)
        printed = self.client.get(reverse("planificacion_obra:materiales_asignados_print"), params, secure=True)
        exported = self.client.get(reverse("planificacion_obra:materiales_asignados_csv"), params, secure=True)
        self.assertNotIn("<th>Precio</th>", self.detail_table(screen.content.decode()))
        self.assertNotContains(printed, "Precio</th>")
        header = exported.content.decode("utf-8-sig").splitlines()[0]
        self.assertNotIn("Precio unitario histórico", header)
        self.assertNotIn("Total neto asignado", header)

    def test_team_scope_applies_to_print_and_csv(self):
        user = get_user_model().objects.create_user(username="materials-v2-outsider")
        user.user_permissions.add(Permission.objects.get(codename="view_tarearecursoreal"))
        self.client.force_login(user)
        for route in ("materiales_asignados_print", "materiales_asignados_csv"):
            response = self.client.get(reverse(f"planificacion_obra:{route}"), {"obra": self.obra.pk}, secure=True)
            self.assertEqual(response.status_code, 404)

    def test_service_query_budget_does_not_grow_per_assignment(self):
        for index in range(1, 6):
            self.real(index=index)
        with CaptureQueriesContext(connection) as small:
            build_materiales_report(self.obra)
        for index in range(6, 51):
            self.real(index=index)
        with CaptureQueriesContext(connection) as large:
            build_materiales_report(self.obra)
        self.assertLessEqual(len(large), len(small) + 1)
        self.assertLessEqual(len(large), 8)
