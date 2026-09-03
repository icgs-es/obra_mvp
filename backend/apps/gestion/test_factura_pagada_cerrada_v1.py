from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import (
    RequestFactory,
    SimpleTestCase,
)

from apps.gestion import factura_cierre
from apps.gestion import urls
from apps.gestion import views


class FacturaPagadaCerradaV2Tests(
    SimpleTestCase,
):
    def request(
        self,
        method="post",
    ):
        request = getattr(
            RequestFactory(),
            method,
        )("/")

        request.user = SimpleNamespace(
            is_authenticated=True
        )

        return request


    def test_pagada_sin_pago_real_no_es_cerrada(
        self,
    ):
        factura = SimpleNamespace(
            estado="PAGADA",
            importe_pagado=0,
            fecha_real_pago=None,
        )

        self.assertFalse(
            factura_cierre.factura_esta_cerrada(
                factura
            )
        )


    def test_pagada_con_importe_pagado_es_cerrada(
        self,
    ):
        factura = SimpleNamespace(
            estado="PAGADA",
            importe_pagado="10.00",
            fecha_real_pago=None,
        )

        self.assertTrue(
            factura_cierre.factura_esta_cerrada(
                factura
            )
        )


    def test_fecha_real_pago_es_evidencia(
        self,
    ):
        factura = SimpleNamespace(
            estado="PAGADA",
            importe_pagado="0.00",
            fecha_real_pago="2026-08-11",
        )

        self.assertTrue(
            factura_cierre.factura_esta_cerrada(
                factura
            )
        )


    def test_pendiente_sin_pago_no_es_cerrada(
        self,
    ):
        factura = SimpleNamespace(
            estado="PENDIENTE",
            importe_pagado="0.00",
            fecha_real_pago=None,
        )

        self.assertFalse(
            factura_cierre.factura_esta_cerrada(
                factura
            )
        )


    @patch(
        "apps.gestion.factura_cierre."
        "FacturaProveedorGestion.objects.filter"
    )
    def test_permite_pagada_sin_pago_real(
        self,
        filter_mock,
    ):
        qs = MagicMock()

        qs.only.return_value.first.return_value = (
            SimpleNamespace(
                pk=4331,
                estado="PAGADA",
                importe_pagado="0.00",
                fecha_real_pago=None,
            )
        )

        filter_mock.return_value = qs

        original = MagicMock(
            return_value=HttpResponse(
                "MODIFICABLE"
            )
        )

        protegida = (
            factura_cierre.crear_guarda(
                original,
                "pk",
            )
        )

        response = protegida(
            self.request(),
            pk=4331,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        original.assert_called_once()


    @patch(
        "apps.gestion.factura_cierre.messages.error"
    )
    @patch(
        "apps.gestion.factura_cierre."
        "FacturaProveedorGestion.objects.filter"
    )
    def test_bloquea_pago_real(
        self,
        filter_mock,
        message_mock,
    ):
        qs = MagicMock()

        qs.only.return_value.first.return_value = (
            SimpleNamespace(
                pk=5000,
                estado="PAGADA",
                importe_pagado="100.00",
                fecha_real_pago=None,
            )
        )

        filter_mock.return_value = qs

        original = MagicMock(
            return_value=HttpResponse(
                "NO DEBE EJECUTAR"
            )
        )

        protegida = (
            factura_cierre.crear_guarda(
                original,
                "pk",
            )
        )

        response = protegida(
            self.request(),
            pk=5000,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        original.assert_not_called()

        message_mock.assert_called_once()


    def test_editar_factura_no_se_bloquea(
        self,
    ):
        self.assertNotIn(
            "factura_update",
            factura_cierre.RUTAS_CERRADAS,
        )


    def test_rutas_documentales_editables_y_financieras_protegidas(
        self,
    ):
        documentales = {
            "factura_linea_create",
            "factura_linea_update",
            "factura_lineas_desde_ocr",
            "factura_importar_desde_albaran",
        }

        protegidas = {
            "factura_delete",
            "factura_linea_delete",
            "factura_recalcular_desde_lineas",
            "factura_lineas_a_almacen",
            "factura_lineas_a_partida",
            "factura_adjunto_upload",
            "factura_adjunto_delete",
            "factura_albaran_desvincular",
            "factura_plan_pagos",
            "factura_vencimiento_marcar_pagado",
        }

        self.assertEqual(
            factura_cierre
            .RUTAS_DOCUMENTALES_EDITABLES_CON_PAGO_REAL,
            documentales,
        )

        self.assertTrue(
            documentales.isdisjoint(
                factura_cierre.RUTAS_CERRADAS
            )
        )

        self.assertTrue(
            protegidas.issubset(
                factura_cierre.RUTAS_CERRADAS
            )
        )


    def test_todas_las_rutas_configuradas_protegidas(
        self,
    ):
        for nombre in factura_cierre.RUTAS_CERRADAS:

            view = getattr(
                views,
                nombre,
            )

            self.assertTrue(
                getattr(
                    view,
                    "_factura_pago_real_guard_v2",
                    False,
                ),
                nombre,
            )


    def test_plan_protegido_solo_post(
        self,
    ):
        self.assertTrue(
            getattr(
                views.factura_plan_pagos,
                "_factura_pagada_solo_post_v1",
                False,
            )
        )
