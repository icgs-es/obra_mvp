from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from apps.gestion.models import (
    AlbaranProveedorGestion,
    AlbaranProveedorLineaGestion,
    ArticuloCompra,
    ArticuloProveedorAlias,
    Proveedor,
)
from apps.gestion.services.articulos_compra import (
    get_or_create_articulo_alias_desde_ocr,
    normalizar_clave_articulo,
)
from planificacion_obra.models import (
    RecursoAlmacenMovimiento,
    RecursoCatalogo,
)
from usuarios.models import Team


class MorteroCatalogCanonicalLinkRepairV1Tests(TestCase):
    def setUp(self):
        self.master_team = Team.objects.create(name="CATALOGO MAESTRO")
        self.team = Team.objects.create(name="EMPRESA ALBARAN")
        self.other_team = Team.objects.create(name="EMPRESA AJENA")
        self.user = get_user_model().objects.create_user(
            username="compras",
            password="test",
        )
        self.team.members.add(self.user)
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="gestion",
                codename="access_gestion",
            )
        )
        self.provider = Proveedor.objects.create(
            team=self.team,
            legacy_id_proveedor=8,
            nombre_comercial="DYPRE S.L.",
            activo=True,
        )
        self.canonical_resource = RecursoCatalogo.objects.create(
            team=self.master_team,
            legacy_id=383,
            nombre="MORTERO M5 - Cubas",
            tipo="MATERIAL",
            unidad="CUBAS",
            stock=Decimal("35.970"),
            control_stock=True,
            observaciones="1 CUBA SON 0,4 TONELADAS",
        )
        self.canonical_article = ArticuloCompra.objects.create(
            team=self.team,
            nombre="MORTERO M5 - Cubas",
            descripcion="1 CUBA SON 0,4 TONELADAS",
            unidad="CUBAS",
            tipo="MATERIAL",
            activo=True,
            recurso_catalogo_id=self.canonical_resource.id,
        )
        self.alias = ArticuloProveedorAlias.objects.create(
            team=self.team,
            proveedor=self.provider,
            articulo=self.canonical_article,
            codigo_proveedor="MORTERO M-5 CUBAS",
            descripcion_proveedor="MORTERO M-5 CUBAS",
            unidad_proveedor="TONELADAS",
            estado=ArticuloProveedorAlias.ESTADO_VINCULADO,
            ultimo_precio=Decimal("45.0000"),
            ultima_fecha=date(2026, 6, 24),
            raw_data={
                "recurso_catalogo_id": self.canonical_resource.id,
                "recurso_legacy_id": 383,
                "historical_duplicate_legacy_id": 4692,
                "factor_compra_por_unidad_uso": "0.4000",
                "factor_unidad_uso_por_compra": "2.5000",
            },
        )
        self.duplicate_resource = RecursoCatalogo.objects.create(
            team=self.master_team,
            legacy_id=4692,
            nombre="MORTERO M-5 CUBAS",
            tipo="MATERIAL",
            unidad="CUBAS",
            stock=Decimal("68.850"),
            control_stock=True,
        )
        self.duplicate_article = ArticuloCompra.objects.create(
            team=self.master_team,
            nombre="MORTERO M-5 CUBAS",
            descripcion="MORTERO M-5 CUBAS",
            unidad="UD",
            tipo="MATERIAL",
            recurso_catalogo_id=self.duplicate_resource.id,
        )
        self.other_mortar = ArticuloCompra.objects.create(
            team=self.team,
            nombre="MORTERO REPARADOR 25 KG",
            unidad="SACO",
            tipo="MATERIAL",
            activo=True,
        )
        self.foreign_article = ArticuloCompra.objects.create(
            team=self.other_team,
            nombre="MORTERO AJENO",
            unidad="SACO",
            tipo="MATERIAL",
            activo=True,
        )
        self.inactive_article = ArticuloCompra.objects.create(
            team=self.team,
            nombre="MORTERO INACTIVO",
            unidad="SACO",
            tipo="MATERIAL",
            activo=False,
        )
        self.albaran = AlbaranProveedorGestion.objects.create(
            team=self.team,
            proveedor=self.provider,
            cod_albaran="26AC01744",
            num_albaran_proveedor="1/00121/13179",
            fecha_albaran=date(2026, 8, 27),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_team_id"] = self.team.id
        session.save()

    def search(self, term):
        response = self.client.get(
            "/app/gestion/articulos/buscar/",
            {
                "q": term,
                "team_id": self.team.id,
                "proveedor_id": self.provider.id,
                "context": "albaran",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def assert_canonical_first(self, term):
        results = self.search(term)
        self.assertTrue(results, term)
        item = results[0]
        self.assertEqual(item["id"], self.canonical_article.id)
        self.assertEqual(item["recurso_catalogo_id"], self.canonical_resource.id)
        self.assertEqual(item["recurso_legacy_id"], 383)
        self.assertEqual(item["codigo"], "383 / 4692")
        self.assertEqual(item["unidad_compra"], "TONELADAS")
        self.assertEqual(item["unidad_uso"], "CUBAS")
        self.assertEqual(item["alias_id"], self.alias.id)
        self.assertIn("Compra: TONELADAS", item["label"])
        self.assertIn("Uso: CUBAS", item["label"])
        return item

    def test_search_variants_resolve_unambiguously_to_canonical(self):
        for term in ("383", "4692", "MORTE", "M-5", "CUBAS"):
            with self.subTest(term=term):
                self.assert_canonical_first(term)

    def test_normalization_equates_only_full_typographic_variants(self):
        expected = "MORTERO M 5 CUBAS"
        for value in (
            "MORTERO M-5 CUBAS",
            "MORTERO M5 CUBAS",
            "MORTERO M 5 CUBAS",
        ):
            self.assertEqual(normalizar_clave_articulo(value), expected)
        self.assertNotEqual(
            normalizar_clave_articulo("MORTERO M-7 CUBAS"),
            expected,
        )

    def test_scope_inactive_distinct_mortar_and_deterministic_limit(self):
        names = [item["nombre"] for item in self.search("MORTERO")]
        self.assertIn("MORTERO M-5 CUBAS", names)
        self.assertIn(self.other_mortar.nombre, names)
        self.assertNotIn(self.foreign_article.nombre, names)
        self.assertNotIn(self.inactive_article.nombre, names)
        first = [item["id"] for item in self.search("MORTERO")]
        second = [item["id"] for item in self.search("MORTERO")]
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 50)

    def test_search_has_bounded_queries_and_does_not_mutate_stock(self):
        with CaptureQueriesContext(connection) as baseline_queries:
            self.search("MORTERO")
        for index in range(20):
            ArticuloCompra.objects.create(
                team=self.team,
                nombre=f"MORTERO DISTINTO {index}",
                unidad="SACO",
                tipo="MATERIAL",
            )
        stock_before = self.canonical_resource.stock
        movements_before = RecursoAlmacenMovimiento.objects.count()
        with CaptureQueriesContext(connection) as queries:
            self.search("MORTERO")
        self.assertLessEqual(len(queries), len(baseline_queries))
        self.assertLessEqual(len(queries), 14)
        self.canonical_resource.refresh_from_db()
        self.assertEqual(self.canonical_resource.stock, stock_before)
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), movements_before)

    def test_manual_fast_create_reuses_normalized_existing_article(self):
        superuser = get_user_model().objects.create_superuser(
            username="root-test",
            email="root@example.com",
            password="test",
        )
        self.client.force_login(superuser)
        counts_before = (
            ArticuloCompra.objects.count(),
            RecursoCatalogo.objects.count(),
            ArticuloProveedorAlias.objects.count(),
        )
        response = self.client.post(
            "/app/gestion/articulos/crear-rapido/",
            {
                "nombre": "MORTERO M 5 CUBAS",
                "team_id": self.team.id,
                "unidad": "TONELADAS",
                "tipo": "MATERIAL",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["created"])
        self.assertEqual(response.json()["item"]["id"], self.canonical_article.id)
        self.assertEqual(
            counts_before,
            (
                ArticuloCompra.objects.count(),
                RecursoCatalogo.objects.count(),
                ArticuloProveedorAlias.objects.count(),
            ),
        )

    def test_legitimate_manual_product_still_creates(self):
        superuser = get_user_model().objects.create_superuser(
            username="root-legit",
            email="legit@example.com",
            password="test",
        )
        self.client.force_login(superuser)
        response = self.client.post(
            "/app/gestion/articulos/crear-rapido/",
            {
                "nombre": "ADITIVO HIDROFUGANTE ESPECIAL",
                "team_id": self.team.id,
                "unidad": "L",
                "tipo": "MATERIAL",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])

    def test_ocr_reuses_article_resource_and_alias(self):
        counts_before = (
            ArticuloCompra.objects.count(),
            RecursoCatalogo.objects.count(),
            ArticuloProveedorAlias.objects.count(),
        )
        article, alias, article_created, alias_created = (
            get_or_create_articulo_alias_desde_ocr(
                team=self.team,
                proveedor=self.provider,
                codigo="MORTERO M5 CUBAS",
                descripcion="MORTERO M 5 CUBAS",
                unidad="TONELADAS",
                precio=Decimal("46.00"),
                fecha=date(2026, 8, 27),
            )
        )
        self.assertEqual(article.id, self.canonical_article.id)
        self.assertEqual(alias.id, self.alias.id)
        self.assertFalse(article_created)
        self.assertFalse(alias_created)
        self.assertEqual(counts_before, (
            ArticuloCompra.objects.count(),
            RecursoCatalogo.objects.count(),
            ArticuloProveedorAlias.objects.count(),
        ))

    def test_line_creation_links_canonical_and_never_changes_stock(self):
        stock_before = self.canonical_resource.stock
        movement_count = RecursoAlmacenMovimiento.objects.count()
        response = self.client.post(
            f"/app/gestion/albaranes/{self.albaran.id}/lineas/nueva/",
            {
                "linea": "1",
                "articulo_compra_id": self.canonical_article.id,
                "articulo_busqueda": "383 / 4692 · MORTERO M-5 CUBAS",
                "codigo": "MORTERO M-5 CUBAS",
                "descripcion": "MORTERO M-5 CUBAS",
                "cantidad": "1",
                "unidad_compra": "TONELADAS",
                "precio_unitario": "45",
                "descuento": "0",
                "importe_descuento": "0",
                "importe_linea": "45",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        line = AlbaranProveedorLineaGestion.objects.get(albaran=self.albaran)
        self.assertEqual(line.articulo_compra_id, self.canonical_article.id)
        self.assertEqual(line.articulo_compra.recurso_catalogo_id, self.canonical_resource.id)
        # El catálogo de unidades conserva el significado documental con su
        # código canónico TN; el autocomplete presenta TONELADAS al usuario.
        self.assertEqual(line.unidad, "TN")
        self.assertFalse(line.en_almacen)
        self.canonical_resource.refresh_from_db()
        self.assertEqual(self.canonical_resource.stock, stock_before)
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), movement_count)

    def test_form_is_ajax_scoped_and_does_not_preload_catalog(self):
        response = self.client.get(
            f"/app/gestion/albaranes/{self.albaran.id}/lineas/nueva/",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("/app/gestion/articulos/buscar/", html)
        self.assertIn(f'const articuloTeamId = "{self.team.id}"', html)
        self.assertIn(f'const articuloProveedorId = "{self.provider.id}"', html)
        self.assertNotIn("MORTERO AJENO", html)

    def test_direct_access_auth_staff_and_csrf_guards(self):
        anonymous = Client()
        response = anonymous.get(
            "/app/gestion/articulos/buscar/",
            {"q": "383", "team_id": self.team.id},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)

        staff = get_user_model().objects.create_user(
            username="staff-no-super",
            password="test",
            is_staff=True,
        )
        self.team.members.add(staff)
        self.client.force_login(staff)
        response = self.client.post(
            "/app/gestion/articulos/crear-rapido/",
            {"nombre": "NO AUTORIZADO", "team_id": self.team.id},
            secure=True,
        )
        self.assertEqual(response.status_code, 403)

        superuser = get_user_model().objects.create_superuser(
            username="csrf-root",
            email="csrf@example.com",
            password="test",
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(superuser)
        response = csrf_client.post(
            "/app/gestion/articulos/crear-rapido/",
            {"nombre": "SIN CSRF", "team_id": self.team.id},
            secure=True,
        )
        self.assertEqual(response.status_code, 403)
