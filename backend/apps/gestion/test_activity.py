from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .activity import (
    registrar_alta_documento_gestion,
)


class GestionActivityAdapterTests(
    SimpleTestCase
):
    def setUp(self):
        self.actor = SimpleNamespace(
            pk=2,
            username="Ivan",
        )

        self.team = SimpleNamespace(
            pk=1,
            name="INVERADRIDE",
        )

        self.provider = SimpleNamespace(
            pk=44,
            nombre_comercial=(
                "CANO MATERIALES"
            ),
            nombre_fiscal="",
        )

    def document(self, **overrides):
        values = {
            "pk": 2191,
            "team": self.team,
            "team_id": self.team.pk,
            "proveedor": self.provider,
            "proveedor_id": self.provider.pk,
            "cod_albaran": "26AC01691",
            "num_albaran_proveedor": (
                "K26010243"
            ),
            "importe_albaran": (
                Decimal("55.24")
            ),
            "cod_factura": "26FC01849",
            "num_factura_proveedor": (
                "FV26/13786"
            ),
            "importe_factura": (
                Decimal("402.57")
            ),
            "raw_data": {},
            "origen_alta": "MANUAL",
            "ambito_gestion": "OBRA",
        }

        values.update(overrides)

        return SimpleNamespace(**values)

    @patch(
        "apps.gestion.activity."
        "registrar_actividad"
    )
    def test_albaran_manual(
        self,
        registrar,
    ):
        document = self.document()

        registrar_alta_documento_gestion(
            documento=document,
            actor=self.actor,
            tipo="albaran",
            origen_flujo="manual",
            tiene_adjunto=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["modulo"],
            "gestion",
        )
        self.assertEqual(
            kwargs["accion"],
            "crear_albaran",
        )
        self.assertEqual(
            kwargs["team"],
            self.team,
        )
        self.assertEqual(
            kwargs["actor"],
            self.actor,
        )
        self.assertIn(
            "26AC01691",
            kwargs["descripcion"],
        )
        self.assertIn(
            "K26010243",
            kwargs["descripcion"],
        )
        self.assertIn(
            "CANO MATERIALES",
            kwargs["descripcion"],
        )
        self.assertIn(
            "55,24 €",
            kwargs["descripcion"],
        )
        self.assertEqual(
            kwargs["clave_idempotencia"],
            "gestion:alta:albaran:2191",
        )

    @patch(
        "apps.gestion.activity."
        "registrar_actividad"
    )
    def test_factura_pdf(
        self,
        registrar,
    ):
        document = self.document(
            pk=4293,
            raw_data={
                "source": "portal_pdf_ocr",
                "created_from": (
                    "gestion_factura_desde_pdf"
                ),
            },
            origen_alta="PDF_OCR",
        )

        registrar_alta_documento_gestion(
            documento=document,
            actor=self.actor,
            tipo="factura",
            origen_flujo="pdf_ocr",
            tiene_adjunto=True,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["accion"],
            "crear_factura",
        )
        self.assertIn(
            "mediante PDF/OCR",
            kwargs["descripcion"],
        )
        self.assertEqual(
            kwargs["metadata"]["flujo"],
            "pdf_ocr",
        )
        self.assertTrue(
            kwargs["metadata"][
                "tiene_adjunto"
            ]
        )
        self.assertEqual(
            kwargs["url"],
            "/app/gestion/facturas/4293/",
        )

    @patch(
        "apps.gestion.activity."
        "registrar_actividad"
    )
    def test_factura_desde_albaranes(
        self,
        registrar,
    ):
        document = self.document(
            pk=4294,
        )

        albaranes = [
            SimpleNamespace(
                pk=10,
                cod_albaran="26AC00010",
            ),
            SimpleNamespace(
                pk=11,
                cod_albaran="26AC00011",
            ),
        ]

        registrar_alta_documento_gestion(
            documento=document,
            actor=self.actor,
            tipo="factura",
            origen_flujo=(
                "desde_albaranes"
            ),
            albaranes=albaranes,
            tiene_adjunto=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertIn(
            "desde 2 albaranes",
            kwargs["descripcion"],
        )
        self.assertEqual(
            kwargs["metadata"][
                "albaran_ids"
            ],
            [10, 11],
        )
        self.assertEqual(
            kwargs["metadata"][
                "albaranes_count"
            ],
            2,
        )

    @patch(
        "apps.gestion.activity."
        "registrar_actividad"
    )
    def test_clave_idempotente_estable(
        self,
        registrar,
    ):
        document = self.document(
            pk=5000,
        )

        for _iteration in range(2):
            registrar_alta_documento_gestion(
                documento=document,
                actor=self.actor,
                tipo="factura",
                origen_flujo="manual",
            )

        keys = [
            call.kwargs[
                "clave_idempotencia"
            ]
            for call in registrar.call_args_list
        ]

        self.assertEqual(
            keys,
            [
                "gestion:alta:factura:5000",
                "gestion:alta:factura:5000",
            ],
        )

    def test_documento_sin_pk_rechazado(
        self,
    ):
        document = self.document(pk=None)

        with self.assertRaises(ValueError):
            registrar_alta_documento_gestion(
                documento=document,
                actor=self.actor,
                tipo="factura",
            )
