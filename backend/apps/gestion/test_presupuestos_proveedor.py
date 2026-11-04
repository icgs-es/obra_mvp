from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Team

from .models import FacturaVencimientoGestion, PresupuestoProveedorGestion, Proveedor


class PresupuestosProveedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Empresa de pruebas")
        cls.otra_empresa = Team.objects.create(name="Otra empresa")
        cls.proveedor = Proveedor.objects.create(
            team=cls.team, legacy_id_proveedor=1, nombre_comercial="Proveedor local",
        )
        cls.proveedor_ajeno = Proveedor.objects.create(
            team=cls.otra_empresa, legacy_id_proveedor=1, nombre_comercial="Proveedor ajeno",
        )
        cls.usuario = get_user_model().objects.create_user(username="compras")
        cls.team.members.add(cls.usuario)
        cls.usuario.user_permissions.add(Permission.objects.get(
            content_type__app_label="gestion", codename="access_gestion",
        ))

    def setUp(self):
        self.client.force_login(self.usuario)

    def alta(self, **changes):
        data = {
            "team_id": self.team.pk, "proveedor": self.proveedor.pk,
            "numero_proveedor": "OF-TEST-002", "concepto": "Barandillas",
            "fecha_entrega": "2026-12-10",
        }
        data.update(changes)
        return self.client.post(reverse("gestion:presupuesto_create"), data)

    def test_total_abierto_y_pdf_privado(self):
        storage = PresupuestoProveedorGestion._meta.get_field("pdf").storage
        with TemporaryDirectory() as folder, patch.object(storage, "location", folder):
            pdf = b"%PDF-1.4\n%%EOF"
            response = self.alta(pdf=SimpleUploadedFile("oferta.pdf", pdf, "application/pdf"))
            self.assertEqual(response.status_code, 302)
            presupuesto = PresupuestoProveedorGestion.objects.get()
            self.assertIsNone(presupuesto.importe_total)
            self.assertTrue(Path(folder, presupuesto.pdf.name).is_file())
            url = reverse("gestion:presupuesto_pdf", args=[presupuesto.pk])
            response = self.client.get(url)
            self.assertEqual(b"".join(response.streaming_content), pdf)
            editar_url = reverse("gestion:presupuesto_update", args=[presupuesto.pk])
            self.assertContains(self.client.get(editar_url), "Descargar PDF actual")
            self.team.members.remove(self.usuario)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_alta_rechaza_proveedor_de_otra_empresa(self):
        response = self.alta(proveedor=self.proveedor_ajeno.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("proveedor", response.context["form"].errors)
        self.assertFalse(PresupuestoProveedorGestion.objects.exists())

    def test_aprobacion_exige_permiso_y_registra_usuario_y_fecha(self):
        self.alta()
        presupuesto = PresupuestoProveedorGestion.objects.get()
        url = reverse("gestion:presupuesto_aprobacion", args=[presupuesto.pk])
        self.assertEqual(self.client.post(url, {"accion": "aprobar"}).status_code, 403)
        self.usuario.groups.add(Group.objects.get(name="Gerencia"))
        self.assertEqual(self.client.post(url, {"accion": "aprobar"}).status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.aprobado_por, self.usuario)
        self.assertIsNotNone(presupuesto.aprobado_en)
        self.assertEqual(presupuesto.nombre_aprobador, "compras")
        self.assertContains(self.client.get(reverse("gestion:presupuestos_list")), "Aprobado")
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_plan_parcial_por_hito_y_rechazo_de_exceso(self):
        self.usuario.groups.add(Group.objects.get(name="Gerencia"))
        self.alta(importe_total="100.00")
        presupuesto = PresupuestoProveedorGestion.objects.get()
        url = reverse("gestion:presupuesto_plan", args=[presupuesto.pk])
        self.assertContains(self.client.get(url), "Añadir pago")
        data = {
            "pagos-TOTAL_FORMS": "2", "pagos-INITIAL_FORMS": "0",
            "pagos-0-hito": "Anticipo", "pagos-0-importe_previsto": "30.00",
        }
        self.assertEqual(self.client.post(url, data).status_code, 302)
        vencimiento = presupuesto.vencimientos.get()
        self.assertEqual(vencimiento.importe_previsto, Decimal("30.00"))
        self.assertIsNone(vencimiento.fecha_vencimiento)
        data.update({"pagos-INITIAL_FORMS": "1", "pagos-0-importe_previsto": "101.00"})
        self.assertContains(self.client.post(url, data), "supera el total")
        self.assertEqual(presupuesto.vencimientos.get(), vencimiento)
        self.assertFalse(FacturaVencimientoGestion.objects.exists())
