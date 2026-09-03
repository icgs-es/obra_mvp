from datetime import date
from decimal import Decimal

from django.test import (
    SimpleTestCase,
    TestCase,
)

from usuarios.models import Team

from apps.gestion.forms import (
    FacturaProveedorLineaForm,
)
from apps.gestion.models import (
    Proveedor,
    ArticuloCompra,
    ArticuloProveedorAlias,
    FacturaProveedorGestion,
    FacturaProveedorLineaGestion,
    AlbaranProveedorGestion,
    AlbaranProveedorLineaGestion,
)
from apps.gestion.purchase_memory_v1 import (
    purchase_suggestion,
)
from apps.gestion.unit_catalog_v1 import (
    normalize_unit,
    unit_choices,
)


class UnitCatalogV1Tests(
    SimpleTestCase
):
    def test_aliases_resolve_same_unit(self):
        for value in (
            "UD",
            "UDS",
            "UN",
            "UNIDAD",
            "UNIDADES",
        ):
            self.assertEqual(
                normalize_unit(value),
                "UD",
            )

    def test_distinct_units_are_not_converted(self):
        self.assertEqual(
            normalize_unit("M3"),
            "M3",
        )

        self.assertEqual(
            normalize_unit("TN"),
            "TN",
        )

        self.assertEqual(
            normalize_unit("CUBAS"),
            "CUBA",
        )

        self.assertNotEqual(
            normalize_unit("M3"),
            normalize_unit("TN"),
        )

        self.assertNotEqual(
            normalize_unit("TN"),
            normalize_unit("CUBAS"),
        )

    def test_choices_do_not_contain_plural_duplicates(self):
        values = [
            value
            for value, _label
            in unit_choices()
        ]

        self.assertIn(
            "UD",
            values,
        )

        self.assertNotIn(
            "UDS",
            values,
        )

        self.assertNotIn(
            "UNIDADES",
            values,
        )

        self.assertNotIn(
            "CUBAS",
            values,
        )


class PurchaseMemoryV1Tests(
    TestCase
):
    def setUp(self):
        self.team = Team.objects.create(
            name="TEST UNIDADES V1A",
        )

        self.provider = Proveedor.objects.create(
            team=self.team,
            legacy_id_proveedor=990001,
            nombre_comercial="PROVEEDOR TEST V1A",
        )

        self.article = ArticuloCompra.objects.create(
            team=self.team,
            nombre="SERVICIO TEST V1A",
            descripcion="",
            unidad="",
            tipo="SERVICIO",
            activo=True,
        )

        self.invoice = (
            FacturaProveedorGestion.objects
            .create(
                team=self.team,
                proveedor=self.provider,
                cod_factura="TEST-FV1A-1",
                num_factura_proveedor="EXT-1",
                fecha_emision=date(
                    2026,
                    7,
                    30,
                ),
            )
        )

    def test_invoice_line_normalizes_and_updates_memory(
        self,
    ):
        line = (
            FacturaProveedorLineaGestion.objects
            .create(
                factura=self.invoice,
                linea=1,
                articulo_compra=self.article,
                cantidad=Decimal("1"),
                unidad_compra="UNIDADES",
                precio_unitario=Decimal(
                    "36.0200"
                ),
                importe_linea=Decimal(
                    "36.02"
                ),
            )
        )

        line.refresh_from_db()
        self.article.refresh_from_db()

        self.assertEqual(
            line.unidad_compra,
            "UD",
        )

        alias = (
            ArticuloProveedorAlias.objects
            .get(
                articulo=self.article,
                proveedor=self.provider,
            )
        )

        self.assertEqual(
            alias.unidad_proveedor,
            "UD",
        )

        self.assertEqual(
            alias.ultimo_precio,
            Decimal("36.0200"),
        )

        self.assertEqual(
            alias.ultima_fecha,
            date(
                2026,
                7,
                30,
            ),
        )

        suggestion = purchase_suggestion(
            article=self.article,
            provider=self.provider,
        )

        self.assertEqual(
            suggestion["precio"],
            Decimal("36.0200"),
        )

        self.assertEqual(
            suggestion["unidad_compra"],
            "UD",
        )

        self.assertEqual(
            suggestion["fuente"],
            "FACTURA",
        )

    def test_zero_price_does_not_create_memory(
        self,
    ):
        article = ArticuloCompra.objects.create(
            team=self.team,
            nombre="SIN PRECIO TEST V1A",
            unidad="UD",
            tipo="MATERIAL",
        )

        FacturaProveedorLineaGestion.objects.create(
            factura=self.invoice,
            linea=2,
            articulo_compra=article,
            cantidad=Decimal("1"),
            unidad_compra="UDS",
            precio_unitario=Decimal("0"),
            importe_linea=Decimal("0"),
        )

        self.assertFalse(
            ArticuloProveedorAlias.objects
            .filter(
                articulo=article,
                proveedor=self.provider,
            )
            .exists()
        )

    def test_invoice_wins_same_date_over_delivery_note(
        self,
    ):
        FacturaProveedorLineaGestion.objects.create(
            factura=self.invoice,
            linea=3,
            articulo_compra=self.article,
            cantidad=Decimal("1"),
            unidad_compra="MES",
            precio_unitario=Decimal(
                "40.0000"
            ),
            importe_linea=Decimal(
                "40.00"
            ),
        )

        delivery_note = (
            AlbaranProveedorGestion.objects
            .create(
                team=self.team,
                proveedor=self.provider,
                cod_albaran="TEST-AV1A-1",
                num_albaran_proveedor="ALB-1",
                fecha_albaran=date(
                    2026,
                    7,
                    30,
                ),
            )
        )

        AlbaranProveedorLineaGestion.objects.create(
            albaran=delivery_note,
            linea=1,
            articulo_compra=self.article,
            cantidad=Decimal("1"),
            unidad="MESES",
            cantidad_compra=Decimal("1"),
            unidad_compra="MESES",
            cantidad_x_unidad=Decimal("1"),
            precio_unitario=Decimal(
                "38.0000"
            ),
            importe_linea=Decimal(
                "38.00"
            ),
        )

        suggestion = purchase_suggestion(
            article=self.article,
            provider=self.provider,
        )

        self.assertEqual(
            suggestion["fuente"],
            "FACTURA",
        )

        self.assertEqual(
            suggestion["precio"],
            Decimal("40.0000"),
        )

        self.assertEqual(
            suggestion["unidad_compra"],
            "MES",
        )

    def test_negative_return_normalizes_unit_without_updating_memory(
        self,
    ):
        article = ArticuloCompra.objects.create(
            team=self.team,
            nombre="DEVOLUCION TEST V1A",
            unidad="UD",
            tipo="MATERIAL",
        )

        delivery_note = (
            AlbaranProveedorGestion.objects
            .create(
                team=self.team,
                proveedor=self.provider,
                cod_albaran="TEST-RETURN-V1A",
                num_albaran_proveedor="RETURN-1",
                fecha_albaran=date(
                    2026,
                    7,
                    31,
                ),
            )
        )

        line = (
            AlbaranProveedorLineaGestion.objects
            .create(
                albaran=delivery_note,
                linea=1,
                articulo_compra=article,
                cantidad=Decimal("-12"),
                unidad="UN",
                cantidad_compra=Decimal("-12"),
                unidad_compra="UNIDADES",
                cantidad_x_unidad=Decimal("1"),
                precio_unitario=Decimal(
                    "2.0660"
                ),
                importe_linea=Decimal(
                    "-19.83"
                ),
            )
        )

        line.refresh_from_db()

        self.assertEqual(
            line.unidad,
            "UD",
        )

        self.assertEqual(
            line.unidad_compra,
            "UD",
        )

        self.assertFalse(
            ArticuloProveedorAlias.objects
            .filter(
                articulo=article,
                proveedor=self.provider,
            )
            .exists()
        )

        suggestion = purchase_suggestion(
            article=article,
            provider=self.provider,
        )

        self.assertIsNone(
            suggestion["precio"]
        )

    def test_invoice_form_has_canonical_choices(
        self,
    ):
        form = FacturaProveedorLineaForm(
            team=self.team,
            factura=self.invoice,
        )

        values = [
            value
            for value, _label
            in form.fields[
                "unidad_compra"
            ].widget.choices
        ]

        self.assertIn(
            "UD",
            values,
        )

        self.assertNotIn(
            "UDS",
            values,
        )

        self.assertNotIn(
            "UNIDADES",
            values,
        )


class AlbaranCompatCanonicalV1Tests(
    TestCase
):
    def setUp(self):
        from django.contrib.auth import (
            get_user_model,
        )
        from django.test import Client

        self.team = Team.objects.create(
            name="TEST ALBARAN COMPAT V1A",
        )

        self.provider = Proveedor.objects.create(
            team=self.team,
            legacy_id_proveedor=990101,
            nombre_comercial=(
                "PROVEEDOR ALBARAN COMPAT V1A"
            ),
        )

        self.delivery_note = (
            AlbaranProveedorGestion.objects
            .create(
                team=self.team,
                proveedor=self.provider,
                cod_albaran="TEST-COMPAT-V1A",
                num_albaran_proveedor=(
                    "EXT-COMPAT-V1A"
                ),
                fecha_albaran=date(
                    2026,
                    7,
                    31,
                ),
            )
        )

        self.user = (
            get_user_model()
            .objects
            .create_superuser(
                username=(
                    "superuser_albaran_compat_v1a"
                ),
                email=(
                    "compat-v1a@example.invalid"
                ),
                password="test-password-v1a",
            )
        )

        self.client = Client()
        self.client.force_login(
            self.user
        )

        session = self.client.session

        for key in (
            "active_team_id",
            "team_id",
            "current_team_id",
        ):
            session[key] = self.team.pk

        session.save()

    def test_real_create_page_uses_canonical_units_and_v1a_ui(
        self,
    ):
        from django.urls import reverse

        response = self.client.get(
            reverse(
                "gestion:albaran_linea_create",
                args=[
                    self.delivery_note.pk
                ],
            ),
            secure=True,
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "GESTION_UNIDADES_COMPRA_V1A_UI",
        )

        self.assertContains(
            response,
            'id="id_unidad_compra"',
        )

        self.assertContains(
            response,
            'value="UD"',
        )

        self.assertContains(
            response,
            'value="CUBA"',
        )

        self.assertContains(
            response,
            'value="TN"',
        )

        self.assertNotContains(
            response,
            'value="UDS"',
        )

        self.assertNotContains(
            response,
            'value="UNIDADES"',
        )

        self.assertNotContains(
            response,
            'value="CUBAS"',
        )

        self.assertNotContains(
            response,
            'value="TONELADAS"',
        )

    def test_real_create_normalizes_alias_before_storage(
        self,
    ):
        from django.urls import reverse

        response = self.client.post(
            reverse(
                "gestion:albaran_linea_create",
                args=[
                    self.delivery_note.pk
                ],
            ),
            {
                "linea": "1",
                "descripcion": (
                    "ARTICULO COMPAT V1A"
                ),
                "cantidad": "2",
                "unidad_compra": (
                    "UNIDADES"
                ),
                "precio_unitario": "10.00",
                "descuento": "0",
            },
            secure=True,
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        line = (
            AlbaranProveedorLineaGestion
            .objects
            .get(
                albaran=self.delivery_note
            )
        )

        self.assertEqual(
            line.unidad,
            "UD",
        )

        self.assertEqual(
            line.unidad_compra,
            "UD",
        )

        self.assertEqual(
            line.cantidad,
            Decimal("2.0000"),
        )

        self.assertEqual(
            line.cantidad_compra,
            Decimal("2.0000"),
        )

        self.assertEqual(
            line.cantidad_x_unidad,
            Decimal("1.0000"),
        )

