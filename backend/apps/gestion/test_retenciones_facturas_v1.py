from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from usuarios.models import Team
from planificacion_obra.models import ObraPlanificacion
from apps.gestion.factura_pagos import validar_plan_pago
from apps.gestion.forms import FacturaProveedorForm
from apps.gestion.models import FacturaProveedorGestion, Proveedor
from apps.gestion.retenciones import aplicar_ocr, calcular, detectar_en_texto


class RetencionCalculoTests(SimpleTestCase):
    def test_caso_referencia_cinco_por_ciento(self):
        result = calcular("23596.04", "4955.17", "5")
        self.assertEqual(result["retencion"], Decimal("1179.80"))
        self.assertEqual(result["total_bruto"], Decimal("28551.21"))
        self.assertEqual(result["importe_a_pagar"], Decimal("27371.41"))

    def test_ocr_reconoce_porcentaje_sin_hardcodear_proveedor(self):
        found = detectar_en_texto("Base 23.596,04 EUR IVA 4.955,17 EUR 5% de Retención")
        self.assertEqual(found["porcentaje"], Decimal("5"))
        payload = aplicar_ocr({"text": "5% de Retención", "base_imponible": "23596.04", "iva": "4955.17"})
        self.assertEqual(payload["retencion"], "1179.80")
        self.assertEqual(payload["total"], "27371.41")

    def test_vencimientos_usan_neto_posterior_a_retencion(self):
        neto = calcular("23596.04", "4955.17", "5")["importe_a_pagar"]
        plan = validar_plan_pago(neto, [{"fecha_vencimiento": date(2026, 9, 30), "importe_previsto": "27371.41"}])
        self.assertEqual(plan[0]["importe_previsto"], Decimal("27371.41"))


class RetencionFormularioTests(TestCase):
    def setUp(self):
        # GESTION_RETENCIONES_OBRA_REQUIRED_FIXTURE_V1
        self.catalog_team = Team.objects.create(
            name="INVERADRIDE",
        )

        self.altoveloo = ObraPlanificacion.objects.create(
            team=self.catalog_team,
            legacy_cod_obra=2,
            codigo="2",
            nombre="ALTOVELOO",
        )

        self.team = Team.objects.create(
            name="Equipo retenciones",
        )

        self.proveedor = Proveedor.objects.create(
            team=self.team,
            legacy_id_proveedor=999991,
            nombre_comercial="Proveedor retenciones",
            aplica_retencion_habitual=True,
            retencion_habitual_porcentaje=Decimal("5.00"),
        )

    def _data(self, **extra):
        data = {
            "proveedor": self.proveedor.id,
            "ambito_gestion": "OBRA",
            "obra_planificacion": self.altoveloo.id,
            "num_factura_proveedor": "RET-TEST-1",
            "fecha_emision": "2026-09-03",
            "importe_base_imponible": "23596.04",
            "iva_porcentaje": "21",
            "retencion_porcentaje": "5",
            "tiene_retencion": "on",
            "estado": "PENDIENTE",
        }
        data.update(extra)
        return data

    def test_edicion_manual_calcula_y_persiste_porcentaje(self):
        form = FacturaProveedorForm(data=self._data(), team=self.team, can_manage_retention=True)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.retencion_porcentaje, Decimal("5.00"))
        self.assertEqual(obj.retencion, Decimal("1179.80"))
        self.assertEqual(obj.importe_factura, Decimal("27371.41"))
        self.assertEqual(form.fields["retencion"].widget.attrs["readonly"], True)

    def test_porcentaje_espanol_y_importes_manipulados_no_prevalecen(self):
        form = FacturaProveedorForm(
            data=self._data(
                retencion_porcentaje="5,00",
                retencion="1,00",
                importe_factura="999.999,99",
            ),
            team=self.team,
            can_manage_retention=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.retencion, Decimal("1179.80"))
        self.assertEqual(obj.importe_factura, Decimal("27371.41"))

    def test_desmarcar_retencion_anula_porcentaje_e_importe_en_servidor(self):
        data = self._data()
        data.pop("tiene_retencion")
        form = FacturaProveedorForm(data=data, team=self.team, can_manage_retention=True)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.retencion_porcentaje, Decimal("0.00"))
        self.assertEqual(obj.retencion, Decimal("0.00"))
        self.assertEqual(obj.importe_factura, Decimal("28551.21"))

    def test_activar_retencion_no_redondea_el_iva_existente(self):
        factura = FacturaProveedorGestion.objects.create(
            team=self.team,
            proveedor=self.proveedor,
            cod_factura="RET-IVA-PRESERVADO",
            num_factura_proveedor="RET-IVA-PRESERVADO",
            fecha_emision=date(2026, 9, 3),
            ambito_gestion="OBRA",
            importe_base_imponible=Decimal("100.00"),
            importe_iva=Decimal("21.01"),
            importe_factura=Decimal("121.01"),
        )
        historical_data = self._data(
            importe_base_imponible="100.00",
            importe_iva="21.01",
            iva_porcentaje="21.01",
            retencion_porcentaje="5",
            num_factura_proveedor="RET-IVA-PRESERVADO",
        )

        # Documento histórico creado antes de que la obra fuese
        # obligatoria: debe seguir siendo editable.
        historical_data.pop(
            "obra_planificacion",
            None,
        )

        form = FacturaProveedorForm(
            data=historical_data,
            instance=factura,
            team=self.team,
            can_manage_retention=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.importe_iva, Decimal("21.01"))
        self.assertEqual(obj.importe_factura, Decimal("116.01"))

    def test_permiso_funcional_no_depende_de_is_staff(self):
        permission = Permission.objects.get(codename="edit_invoice_withholding")
        group, _ = Group.objects.get_or_create(name="Administracion")
        group.permissions.add(permission)
        user = get_user_model().objects.create_user(username="retencion-operativa")
        user.groups.add(group)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.has_perm("gestion.edit_invoice_withholding"))

    def test_ocr_prevalece_sobre_retencion_habitual_distinta(self):
        payload = aplicar_ocr({"text": "3% de Retención", "base_imponible": "100", "iva": "21"}, self.proveedor)
        self.assertEqual(payload["retencion_porcentaje"], "3.00")
        self.assertIn("priorizado el PDF", payload["retencion_aviso"])


class RetencionEditarFacturaUITests(SimpleTestCase):
    def test_ui_activa_enfoca_y_bloquea_importe_derivado(self):
        template = Path(__file__).resolve().parents[2] / "templates" / "gestion" / "factura_form.html"
        source = template.read_text(encoding="utf-8")
        self.assertIn("syncRetencionState", source)
        self.assertIn("retPctInput.disabled = !activa", source)
        self.assertIn("retPctInput.focus(); retPctInput.select()", source)
        self.assertIn('toLocaleString("es-ES"', source)
