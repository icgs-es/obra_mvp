from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .services import (
    get_article,
    render_markdown_safe,
    search_articles,
    validate_library,
)


class AyudaInternaV1Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ayuda-user",
            password="test-password",
        )

    def _grant_gestion(self):
        permission = Permission.objects.get(
            content_type__app_label="gestion",
            codename="access_gestion",
        )

        self.user.user_permissions.add(
            permission
        )

    def test_library_is_valid(self):
        articles = validate_library()

        self.assertGreaterEqual(
            len(articles),
            4,
        )

    def test_unsaved_user_is_fail_closed(self):
        unsaved_user = get_user_model()(
            username="unsaved-help-user",
        )

        article = get_article(
            "gestion.facturacion.planes_pago",
            unsaved_user,
        )

        self.assertIsNone(article)

    def test_facturacion_requires_permission(self):
        article = get_article(
            "gestion.facturacion.planes_pago",
            self.user,
        )

        self.assertIsNone(article)

        self._grant_gestion()

        # AYUDA_TEST_PERMISSION_CACHE_FIX1
        # La primera consulta inicializa la caché de permisos
        # del objeto User. Se recupera una instancia nueva para
        # reproducir el comportamiento de una petición posterior.
        self.user = (
            get_user_model()
            .objects
            .get(pk=self.user.pk)
        )

        article = get_article(
            "gestion.facturacion.planes_pago",
            self.user,
        )

        self.assertIsNotNone(article)

    def test_search_finds_payment_plan(self):
        self._grant_gestion()

        results = search_articles(
            "autorizar plan de pagos",
            self.user,
            context_path=(
                "/app/gestion/facturas/4305/"
            ),
        )

        identifiers = [
            result["id"]
            for result in results
        ]

        self.assertIn(
            "gestion.facturacion.planes_pago",
            identifiers,
        )

    def test_markdown_renderer_escapes_html(self):
        html = render_markdown_safe(
            "# Prueba\n<script>alert(1)</script>"
        )

        self.assertNotIn(
            "<script>",
            html,
        )

        self.assertIn(
            "&lt;script&gt;",
            html,
        )

    def test_article_panel_api(self):
        self._grant_gestion()

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "ayuda:articulo_api",
                kwargs={
                    "article_id": (
                        "gestion.facturacion."
                        "planes_pago"
                    )
                },
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertEqual(
            payload["articulo"]["id"],
            (
                "gestion.facturacion."
                "planes_pago"
            ),
        )

        self.assertIn(
            "Planes de pago",
            payload["articulo"]["html"],
        )

    def test_core_library_module_coverage(self):
        articles = validate_library()

        modules = {
            article.module
            for article in articles
        }

        expected = {
            "General",
            "Gestión",
            "Archivos",
            "Trabajo",
            "Obra",
            "CRM",
            "Correo",
            "INTASA IA",
            "Activos",
            "Informes",
        }

        self.assertTrue(
            expected.issubset(modules)
        )

        self.assertGreaterEqual(
            len(articles),
            39,
        )

    def test_archivos_folder_upload_search(self):
        results = search_articles(
            "subir carpeta",
            self.user,
            context_path="/app/archivos/",
        )

        identifiers = {
            result["id"]
            for result in results
        }

        self.assertIn(
            "archivos.subir_carpetas",
            identifiers,
        )

    def test_obra_warehouse_search(self):
        results = search_articles(
            "movimiento de almacén",
            self.user,
            context_path=(
                "/app/planificacion-obra/"
                "almacen/movimientos/"
            ),
        )

        identifiers = {
            result["id"]
            for result in results
        }

        self.assertIn(
            "obra.almacen_movimientos",
            identifiers,
        )

    def test_center_and_api(self):
        self._grant_gestion()

        self.client.force_login(
            self.user
        )

        center = self.client.get(
            reverse("ayuda:centro"),
            secure=True,
        )

        self.assertEqual(
            center.status_code,
            200,
        )

        api = self.client.get(
            reverse("ayuda:buscar_api"),
            {
                "q": "vencimiento",
                "context": (
                    "/app/gestion/facturas/"
                ),
            },
            secure=True,
        )

        self.assertEqual(
            api.status_code,
            200,
        )

        payload = api.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertGreater(
            payload["total"],
            0,
        )
