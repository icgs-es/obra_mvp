from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.gestion import views
from apps.gestion.models import (
    FacturaProveedorGestion,
    FacturaProveedorLineaGestion,
)
from usuarios.models import Team


class FacturaAbonoSignosLineasV1Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="factura-signos-v1",
            password="test-password",
        )
        self.team = Team.objects.create(name="Equipo signos factura v1")

    def _factura(self, subtipo="ABONO"):
        return FacturaProveedorGestion.objects.create(
            team=self.team,
            cod_factura=f"SIGNOS-{subtipo}-{FacturaProveedorGestion.objects.count()}",
            fecha_emision="2026-09-02",
            importe_base_imponible=Decimal("0.00"),
            importe_iva=Decimal("0.00"),
            importe_factura=Decimal("0.00"),
            subtipo_rectificativa=subtipo,
            creado_por=self.user,
            modificado_por=self.user,
        )

    def _linea(self, factura, numero, base, iva="21.00"):
        base = Decimal(base)
        iva_pct = Decimal(iva)
        iva_importe = (base * iva_pct / Decimal("100")).quantize(Decimal("0.01"))
        return FacturaProveedorLineaGestion.objects.create(
            factura=factura,
            linea=numero,
            cantidad=Decimal("1.0000"),
            precio_unitario=base,
            importe_linea=base,
            raw_data={
                "iva_porcentaje": str(iva_pct),
                "importe_iva_linea": str(iva_importe),
                "total_linea_con_iva": str(base + iva_importe),
            },
        )

    def _recalcular(self, factura):
        return views._gestion_factura_aplicar_totales_agrupados_v1(
            factura,
            source="test_signos_documentales_v1",
        )

    def test_abono_mixto_conserva_lineas_positivas_y_negativas(self):
        factura = self._factura("ABONO")
        self._linea(factura, 1, "-70.47")
        self._linea(factura, 2, "38.00")

        self._recalcular(factura)
        factura.refresh_from_db()

        self.assertEqual(factura.importe_base_imponible, Decimal("-32.47"))
        self.assertEqual(factura.importe_iva, Decimal("-6.82"))
        self.assertEqual(factura.importe_factura, Decimal("-39.29"))

    def test_abono_integramente_negativo_permanece_negativo(self):
        factura = self._factura("ABONO")
        self._linea(factura, 1, "-100.00")

        self._recalcular(factura)
        factura.refresh_from_db()

        self.assertEqual(factura.importe_base_imponible, Decimal("-100.00"))
        self.assertEqual(factura.importe_iva, Decimal("-21.00"))
        self.assertEqual(factura.importe_factura, Decimal("-121.00"))

    def test_factura_ordinaria_positiva_permanece_positiva(self):
        factura = self._factura("")
        self._linea(factura, 1, "100.00")

        self._recalcular(factura)
        factura.refresh_from_db()

        self.assertEqual(factura.importe_base_imponible, Decimal("100.00"))
        self.assertEqual(factura.importe_iva, Decimal("21.00"))
        self.assertEqual(factura.importe_factura, Decimal("121.00"))
