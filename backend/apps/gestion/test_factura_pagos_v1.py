from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from usuarios.models import Team

from apps.gestion.factura_pagos import (
    autorizar_plan_pago,
    registrar_pago_vencimiento,
    validar_plan_pago,
)
from apps.gestion.forms_pagos import PlanPagoLineaForm
from apps.gestion.models import FacturaProveedorGestion, FacturaProveedorLineaGestion


class FacturaPagosMultiplesV1Tests(
    SimpleTestCase
):
    def test_plan_tres_vencimientos(self):
        result = validar_plan_pago(
            Decimal("300.00"),
            [
                {
                    "fecha_vencimiento": (
                        date(2026, 8, 30)
                    ),
                    "importe_previsto": "100",
                },
                {
                    "fecha_vencimiento": (
                        date(2026, 9, 30)
                    ),
                    "importe_previsto": "100",
                },
                {
                    "fecha_vencimiento": (
                        date(2026, 10, 30)
                    ),
                    "importe_previsto": "100",
                },
            ],
        )

        self.assertEqual(
            len(result),
            3,
        )
        self.assertEqual(
            sum(
                item["importe_previsto"]
                for item in result
            ),
            Decimal("300.00"),
        )

    def test_suma_debe_coincidir(self):
        with self.assertRaises(
            ValidationError
        ):
            validar_plan_pago(
                Decimal("300.00"),
                [
                    {
                        "fecha_vencimiento": (
                            date(2026, 8, 30)
                        ),
                        "importe_previsto": "99",
                    },
                ],
            )

    def test_importe_cero_no_permitido(self):
        with self.assertRaises(
            ValidationError
        ):
            validar_plan_pago(
                Decimal("100.00"),
                [
                    {
                        "fecha_vencimiento": (
                            date(2026, 8, 30)
                        ),
                        "importe_previsto": "0",
                    },
                ],
            )


    def test_forma_pago_en_plan_v1b(self):
        result = validar_plan_pago(
            Decimal("100.00"),
            [
                {
                    "fecha_vencimiento": (
                        date(2026, 8, 30)
                    ),
                    "importe_previsto": "100",
                    "forma_pago": "TRANSFERENCIA",
                },
            ],
        )

        self.assertEqual(
            result[0]["forma_pago"],
            "TRANSFERENCIA",
        )

    def test_abono_admite_vencimiento_negativo_por_transferencia(self):
        result = validar_plan_pago(
            Decimal("-100.00"),
            [{
                "fecha_vencimiento": date(2026, 8, 30),
                "importe_previsto": "-100",
                "forma_pago": "TRANSFERENCIA",
            }],
        )
        self.assertEqual(result[0]["importe_previsto"], Decimal("-100.00"))

    def test_formulario_admite_importe_negativo_para_abono(self):
        form = PlanPagoLineaForm(data={
            "fecha_vencimiento": "2026-08-30",
            "importe_previsto": "-100.00",
            "forma_pago": "DEVOLUCION",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_abono_rechaza_forma_pago_no_devolutiva(self):
        with self.assertRaises(ValidationError):
            validar_plan_pago(
                Decimal("-100.00"),
                [{
                    "fecha_vencimiento": date(2026, 8, 30),
                    "importe_previsto": "-100",
                    "forma_pago": "CONTADO",
                }],
            )

    def test_abono_rechaza_vencimiento_positivo(self):
        with self.assertRaises(ValidationError):
            validar_plan_pago(
                Decimal("-100.00"),
                [{
                    "fecha_vencimiento": date(2026, 8, 30),
                    "importe_previsto": "100",
                    "forma_pago": "DEVOLUCION",
                }],
            )


class FacturaAbonoPlanWorkflowTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Equipo abonos pagos")
        self.user = get_user_model().objects.create_user(username="abono-pagos")
        self.user.teams.add(self.team)
        self.factura = FacturaProveedorGestion.objects.create(
            team=self.team,
            cod_factura="ABONO-PLAN-1",
            importe_base_imponible=Decimal("-100.00"),
            importe_iva=Decimal("-21.00"),
            importe_factura=Decimal("-121.00"),
            estado="PENDIENTE",
            subtipo_rectificativa="ABONO",
        )
        FacturaProveedorLineaGestion.objects.create(
            factura=self.factura,
            linea=1,
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal("-100.0000"),
            importe_linea=Decimal("-100.00"),
            raw_data={
                "iva_porcentaje": "21.00",
                "importe_iva_linea": "-21.00",
                "total_linea_con_iva": "-121.00",
            },
        )

    def test_abono_autorizado_y_devuelto_pasa_a_pagada(self):
        factura = autorizar_plan_pago(
            factura_id=self.factura.pk,
            user=self.user,
            team_ids=[self.team.pk],
            lineas=[{
                "fecha_vencimiento": date(2026, 8, 30),
                "importe_previsto": "-121.00",
                "forma_pago": "DEVOLUCION",
                "observaciones": "Abono recibido por transferencia",
            }],
        )
        self.assertEqual(factura.estado, "AUT. PAGO")
        vencimiento = factura.vencimientos_pago.get()

        factura = registrar_pago_vencimiento(
            vencimiento_id=vencimiento.pk,
            user=self.user,
            fecha_real_pago=date(2026, 8, 30),
            referencia_pago="DEV-REF-1",
            team_ids=[self.team.pk],
        )
        vencimiento.refresh_from_db()
        self.assertEqual(vencimiento.importe_pagado, Decimal("-121.00"))
        self.assertEqual(vencimiento.estado, "PAGADO")
        self.assertEqual(factura.importe_pagado, Decimal("-121.00"))
        self.assertEqual(factura.estado, "PAGADA")

    def test_plan_se_bloquea_si_cabecera_y_lineas_no_cuadran(self):
        self.factura.importe_factura = Decimal("-120.00")
        self.factura.save(update_fields=["importe_factura"])
        with self.assertRaises(ValidationError):
            autorizar_plan_pago(
                factura_id=self.factura.pk,
                user=self.user,
                team_ids=[self.team.pk],
                lineas=[{
                    "fecha_vencimiento": date(2026, 8, 30),
                    "importe_previsto": "-120.00",
                    "forma_pago": "DEVOLUCION",
                    "observaciones": "",
                }],
            )
