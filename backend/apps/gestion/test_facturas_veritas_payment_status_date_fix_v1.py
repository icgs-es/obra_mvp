from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.gestion.factura_pagos import corregir_estado_pago_sin_evidencia
from apps.gestion.forms import FacturaProveedorForm
from apps.gestion.models import FacturaProveedorGestion, FacturaVencimientoGestion
from usuarios.models import Team


class FacturasVeritasPaymentStatusDateFixV1Tests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Veritas test")
        self.user = get_user_model().objects.create_user(username="veritas-test", password="x")
        self.team.members.add(self.user)

    def factura(self, **kwargs):
        values = dict(
            team=self.team,
            cod_factura="TEST-VERITAS-1",
            fecha_emision=date(2026, 8, 15),
            importe_factura=Decimal("100.00"),
            importe_pagado=Decimal("0.00"),
            estado="PAGADA",
        )
        values.update(kwargs)
        return FacturaProveedorGestion.objects.create(**values)

    def test_existing_date_renders_iso_value_for_date_input(self):
        f = self.factura()
        form = FacturaProveedorForm(instance=f, team=self.team)
        html = str(form["fecha_emision"])
        self.assertIn('type="date"', html)
        self.assertIn('value="2026-08-15"', html)

    def test_get_form_does_not_mutate_date(self):
        f = self.factura()
        before = f.fecha_emision
        form = FacturaProveedorForm(instance=f, team=self.team)
        self.assertEqual(form.instance.refresh_from_db(), None)
        self.assertEqual(FacturaProveedorGestion.objects.get(pk=f.pk).fecha_emision, before)

    def test_safe_correction_requires_no_payment_evidence(self):
        f = self.factura()
        v = FacturaVencimientoGestion.objects.create(
            team=self.team, factura=f, numero_pago=1,
            fecha_vencimiento=date(2026, 9, 15), importe_previsto=Decimal("100.00"),
            estado=FacturaVencimientoGestion.ESTADO_PENDIENTE,
        )
        changed, did_change = corregir_estado_pago_sin_evidencia(
            factura_id=f.pk, user=self.user, team_ids=[self.team.pk]
        )
        self.assertTrue(did_change)
        self.assertEqual(changed.estado, "PENDIENTE")
        self.assertEqual(FacturaProveedorGestion.objects.get(pk=f.pk).importe_factura, Decimal("100.00"))
        v.refresh_from_db()
        self.assertEqual(v.estado, FacturaVencimientoGestion.ESTADO_PENDIENTE)

    def test_safe_correction_blocks_paid_invoice(self):
        f = self.factura(importe_pagado=Decimal("1.00"))
        with self.assertRaises(ValidationError):
            corregir_estado_pago_sin_evidencia(
                factura_id=f.pk, user=self.user, team_ids=[self.team.pk]
            )
        f.refresh_from_db()
        self.assertEqual(f.estado, "PAGADA")

    def test_correction_is_idempotent_when_already_pending(self):
        f = self.factura(estado="PENDIENTE")
        _f, changed = corregir_estado_pago_sin_evidencia(
            factura_id=f.pk, user=self.user, team_ids=[self.team.pk]
        )
        self.assertFalse(changed)

from apps.gestion.factura_pagos import revertir_pago_erroneo


class FacturasVeritasReversalV2Tests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Veritas reversal test")
        self.user = get_user_model().objects.create_user(username="veritas-reversal", password="x")
        self.team.members.add(self.user)

    def test_reversal_clears_derived_markers_and_preserves_invoice_amount(self):
        f = FacturaProveedorGestion.objects.create(
            team=self.team, cod_factura="REV-1", fecha_emision=date(2026, 6, 26),
            importe_factura=Decimal("508.20"), importe_pagado=Decimal("508.20"),
            fecha_real_pago=date(2026, 8, 17), estado="PAGADA",
        )
        v = FacturaVencimientoGestion.objects.create(
            team=self.team, factura=f, numero_pago=1,
            fecha_vencimiento=date(2026, 8, 17), importe_previsto=Decimal("508.20"),
            estado=FacturaVencimientoGestion.ESTADO_PAGADO,
            importe_pagado=Decimal("508.20"), fecha_real_pago=date(2026, 8, 17),
            pagado_por=self.user,
        )
        result, changed = revertir_pago_erroneo(factura_id=f.pk, user=self.user, team_ids=[self.team.pk])
        self.assertTrue(changed)
        result.refresh_from_db(); v.refresh_from_db()
        self.assertEqual(result.estado, "PENDIENTE")
        self.assertEqual(result.importe_pagado, Decimal("0.00"))
        self.assertIsNone(result.fecha_real_pago)
        self.assertEqual(result.importe_factura, Decimal("508.20"))
        self.assertEqual(v.estado, FacturaVencimientoGestion.ESTADO_PENDIENTE)
        self.assertEqual(v.importe_pagado, Decimal("0.00"))
        self.assertIsNone(v.fecha_real_pago)
        self.assertIsNone(v.pagado_por_id)

    def test_independent_reference_blocks_reversal(self):
        f = FacturaProveedorGestion.objects.create(
            team=self.team, cod_factura="REV-2", importe_factura=Decimal("10.00"),
            importe_pagado=Decimal("10.00"), fecha_real_pago=date(2026, 8, 1),
            estado="PAGADA", raw_data={"transferencia_id": "bank-1"},
        )
        with self.assertRaises(ValidationError):
            revertir_pago_erroneo(factura_id=f.pk, user=self.user, team_ids=[self.team.pk])
        f.refresh_from_db(); self.assertEqual(f.estado, "PAGADA")

    def test_reversal_is_idempotent(self):
        f = FacturaProveedorGestion.objects.create(
            team=self.team, cod_factura="REV-3", importe_factura=Decimal("10.00"),
            importe_pagado=Decimal("10.00"), fecha_real_pago=date(2026, 8, 1), estado="PAGADA",
        )
        _f, first = revertir_pago_erroneo(factura_id=f.pk, user=self.user, team_ids=[self.team.pk])
        _f, second = revertir_pago_erroneo(factura_id=f.pk, user=self.user, team_ids=[self.team.pk])
        self.assertTrue(first); self.assertFalse(second)
