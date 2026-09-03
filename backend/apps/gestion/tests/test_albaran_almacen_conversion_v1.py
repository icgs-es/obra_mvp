from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.gestion.albaran_almacen_conversion import (
    AlbaranAlmacenConversionError,
    conversion_compra_a_uso,
)
from apps.gestion.models import (
    AlbaranProveedorGestion,
    AlbaranProveedorLineaGestion,
    ArticuloCompra,
    ArticuloProveedorAlias,
    Proveedor,
)
from planificacion_obra.models import (
    AlmacenObra,
    ObraPlanificacion,
    RecursoAlmacenMovimiento,
    RecursoCatalogo,
)
from usuarios.models import Team


class AlbaranAlmacenConversionV1Tests(TestCase):
    def setUp(self):
        self.catalog_team = Team.objects.create(name="CATALOGO")
        self.document_team = Team.objects.create(name="COMPRAS")
        self.other_team = Team.objects.create(name="AJENA")
        self.user = get_user_model().objects.create_user(
            username="almacen-user",
            password="test",
        )
        self.document_team.members.add(self.user)
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="gestion",
                codename="access_gestion",
            )
        )
        self.provider = Proveedor.objects.create(
            team=self.document_team,
            legacy_id_proveedor=8,
            nombre_comercial="Proveedor de prueba",
            activo=True,
        )
        self.work = ObraPlanificacion.objects.create(
            team=self.catalog_team,
            legacy_cod_obra=2,
            codigo="OBRA-2",
            nombre="Obra de prueba",
        )
        self.warehouse = AlmacenObra.objects.create(
            team=self.catalog_team,
            obra=self.work,
            legacy_id_almacen="A05",
            nombre="SILO MORTERO",
            descuenta_stock=True,
        )
        self.resource = RecursoCatalogo.objects.create(
            team=self.catalog_team,
            legacy_id=383,
            nombre="Mortero de prueba",
            tipo="MATERIAL",
            unidad="CUBAS",
            stock=Decimal("35.970"),
            control_stock=True,
        )
        self.article = ArticuloCompra.objects.create(
            team=self.document_team,
            nombre="Mortero de prueba",
            unidad="CUBAS",
            tipo="MATERIAL",
            activo=True,
            recurso_catalogo_id=self.resource.id,
        )
        self.alias = ArticuloProveedorAlias.objects.create(
            team=self.document_team,
            proveedor=self.provider,
            articulo=self.article,
            codigo_proveedor="MORTERO",
            descripcion_proveedor="MORTERO",
            unidad_proveedor="TONELADAS",
            estado=ArticuloProveedorAlias.ESTADO_VINCULADO,
            raw_data={
                "recurso_catalogo_id": self.resource.id,
                "factor_compra_por_unidad_uso": "0,4",
                "factor_unidad_uso_por_compra": "2,5",
            },
        )
        self.albaran = AlbaranProveedorGestion.objects.create(
            team=self.document_team,
            proveedor=self.provider,
            cod_albaran="TEST-ALB-1",
            num_albaran_proveedor="TEST-1",
            fecha_albaran=date(2026, 8, 27),
        )
        self.line = AlbaranProveedorLineaGestion.objects.create(
            albaran=self.albaran,
            linea=1,
            articulo_compra=self.article,
            cantidad=Decimal("27.5200"),
            cantidad_compra=Decimal("27.5200"),
            unidad="TN",
            unidad_compra="TN",
            precio_unitario=Decimal("45.0000"),
            importe_linea=Decimal("1238.40"),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_team_id"] = str(self.document_team.pk)
        session.save()

    @property
    def url(self):
        return reverse("gestion:albaran_lineas_a_almacen", args=[self.albaran.pk])

    def payload(self, **overrides):
        data = {
            "almacen_id": str(self.warehouse.pk),
            f"sel_{self.line.pk}": "on",
            # Deliberately wrong browser values: the server must ignore them.
            f"cantidad_uso_{self.line.pk}": "27,5200",
            f"unidad_uso_{self.line.pk}": "TN",
            f"precio_uso_{self.line.pk}": "45,0000",
        }
        data.update(overrides)
        return data

    def test_canonical_mortar_conversion_is_shown_and_persisted(self):
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "68.8000")
        self.assertContains(response, "18.0000")

        stock_before = self.resource.stock
        response = self.client.post(self.url, self.payload(), secure=True)
        self.assertEqual(response.status_code, 302)

        movement = RecursoAlmacenMovimiento.objects.get(
            raw_data__albaran_linea_id=self.line.id
        )
        self.resource.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(movement.recurso_id, self.resource.id)
        self.assertEqual(movement.unidad, "CUBAS")
        self.assertEqual(movement.cantidad, Decimal("68.8000"))
        self.assertEqual(movement.raw_data["precio_unitario_uso"], "18.0000")
        self.assertEqual(movement.raw_data["importe_uso"], "1238.40")
        self.assertEqual(movement.fecha_movimiento, date(2026, 8, 27))
        self.assertEqual(self.resource.stock, stock_before + Decimal("68.8000"))
        self.assertTrue(self.line.en_almacen)
        self.assertEqual(self.line.raw_data["movimiento_almacen_id"], movement.id)

    def test_second_post_resynchronizes_without_another_stock_increment(self):
        self.client.post(self.url, self.payload(), secure=True)
        self.resource.refresh_from_db()
        stock_after_first = self.resource.stock
        response = self.client.post(self.url, self.payload(), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            RecursoAlmacenMovimiento.objects.filter(
                raw_data__albaran_linea_id=self.line.id
            ).count(),
            1,
        )
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.stock, stock_after_first)

    def test_existing_documentary_movement_resynchronizes_without_stock_change(self):
        existing = RecursoAlmacenMovimiento.objects.create(
            team=self.catalog_team,
            legacy_id_movimiento=9001,
            almacen=self.warehouse,
            recurso=self.resource,
            obra=self.work,
            unidad="CUBAS",
            cantidad=Decimal("68.8000"),
            quedan=Decimal("104.7700"),
            fecha_movimiento=self.albaran.fecha_albaran,
            tipo_movimiento="ENTRADA",
            cod_albaran=self.albaran.cod_albaran,
            linea=self.line.linea,
            raw_data={
                "albaran_id": self.albaran.id,
                "albaran_linea_id": self.line.id,
            },
        )
        stock_before = self.resource.stock
        response = self.client.post(self.url, self.payload(), secure=True)
        self.assertEqual(response.status_code, 302)
        self.line.refresh_from_db()
        self.resource.refresh_from_db()
        self.assertEqual(self.line.raw_data["movimiento_almacen_id"], existing.id)
        self.assertTrue(self.line.en_almacen)
        self.assertEqual(self.resource.stock, stock_before)
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), 1)

    def test_invalid_factor_renders_functional_error_without_writing(self):
        self.alias.raw_data["factor_unidad_uso_por_compra"] = "0"
        self.alias.save(update_fields=["raw_data"])
        stock_before = self.resource.stock
        response = self.client.post(self.url, self.payload(), secure=True, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "factores de conversión deben ser positivos")
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), 0)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.stock, stock_before)

    def test_no_document_date_blocks_without_writing(self):
        self.albaran.fecha_albaran = None
        self.albaran.save(update_fields=["fecha_albaran"])
        response = self.client.post(self.url, self.payload(), secure=True, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "debe tener fecha")
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), 0)

    def test_team_scope_and_staff_without_membership_are_rejected(self):
        outsider = get_user_model().objects.create_user(
            username="outsider",
            password="test",
            is_staff=True,
        )
        outsider.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="gestion",
                codename="access_gestion",
            )
        )
        self.client.force_login(outsider)
        response = self.client.post(self.url, self.payload(), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), 0)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, self.payload(), secure=True)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(RecursoAlmacenMovimiento.objects.count(), 0)


class CanonicalConversionUnitTests(TestCase):
    def make_alias(self, raw_data):
        return type(
            "Alias",
            (),
            {
                "pk": 571,
                "unidad_proveedor": "TONELADAS",
                "raw_data": raw_data,
            },
        )()

    def convert(self, raw_data):
        return conversion_compra_a_uso(
            cantidad_compra="27,5200",
            unidad_compra="TN",
            precio_compra="45,0000",
            importe_compra="1.238,40",
            unidad_uso="CUBAS",
            alias=self.make_alias(raw_data),
            recurso_id=4455,
        )

    def test_decimal_mortar_conversion_preserves_amount(self):
        result = self.convert({
            "recurso_catalogo_id": 4455,
            "factor_compra_por_unidad_uso": "0.4",
            "factor_unidad_uso_por_compra": "2.5",
        })
        self.assertEqual(result.cantidad_uso, Decimal("68.8000"))
        self.assertEqual(result.precio_uso, Decimal("18.0000"))
        self.assertEqual(result.importe_uso, Decimal("1238.40"))

    def test_zero_negative_and_non_reciprocal_factors_are_rejected(self):
        cases = (
            ("0", "0.4"),
            ("-2.5", "-0.4"),
            ("2.5", "0.5"),
        )
        for usage, purchase in cases:
            with self.subTest(usage=usage, purchase=purchase):
                with self.assertRaises(AlbaranAlmacenConversionError):
                    self.convert({
                        "recurso_catalogo_id": 4455,
                        "factor_unidad_uso_por_compra": usage,
                        "factor_compra_por_unidad_uso": purchase,
                    })

    def test_incompatible_or_wrong_resource_is_rejected(self):
        with self.assertRaises(AlbaranAlmacenConversionError):
            self.convert({})
        with self.assertRaises(AlbaranAlmacenConversionError):
            self.convert({
                "recurso_catalogo_id": 8685,
                "factor_unidad_uso_por_compra": "2.5",
                "factor_compra_por_unidad_uso": "0.4",
            })
