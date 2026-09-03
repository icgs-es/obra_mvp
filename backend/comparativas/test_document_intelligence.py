from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from .document_intelligence import (
    BUDGET_DOCUMENT_SCHEMA,
    BUDGET_DOCUMENT_SCHEMA_NAME,
    MAX_SOURCE_TEXT_CHARS,
    BudgetDocumentIntelligenceError,
    analyze_budget_document,
    build_budget_document_instructions,
)


SOURCE_TEXT = """
PROVEEDORA A LA INDUSTRIA Y CONSTRUCCION, S.A. A29049509
INVERADRIDE GESTION S.L. CIF/NIF B02703833
Oferta Nº 26-101109
FECHA: 31/08/26
REFERENCIA DESCRIPCIÓN CDAD. Unidad PRECIO IMPORTE
DU03P8080BL STONE PL PLT DCH 80X80 PZ BL 2 Unidad 83,20 166,40
DU03P10080BL STONE PL PLT DCH 100X80 PZ BL 1 Unidad 104,00 104,00
DU03P14080BL STONE PL PLT DCH 140X80 PZ BL 1 Unidad 145,60 145,60
Total EUR 416,00
Importe IVA+RE 87,36
Total EUR incl. IVA 503,36
Forma pago 60 DIAS
Pago por giro
Condiciones envío Recogida en N/Almacen
Validez de la Oferta: 30 días
Vendedor: Persona de ventas
C/ DIRECCION DEL CLIENTE
""".strip()


def valid_data():
    return {
        "documento": {
            "proveedor_emisor": "PROVEEDORA A LA INDUSTRIA Y CONSTRUCCION, S.A.",
            "nif_cif": "A29049509",
            "numero": "26-101109",
            "fecha": "2026-08-31",
        },
        "cliente": {
            "nombre": "INVERADRIDE GESTION S.L.",
            "nif_cif": "B02703833",
            "direccion": "C/ DIRECCION DEL CLIENTE",
        },
        "economia": {
            "base": "416.00",
            "iva": "87.36",
            "total": "503.36",
            "moneda": "EUR",
        },
        "partidas": [
            {
                "descripcion": "STONE PL PLT DCH 80X80 PZ BL",
                "codigo": "DU03P8080BL",
                "cantidad": "2",
                "unidad": "Unidad",
                "precio_unitario": "83.20",
                "importe": "166.40",
                "alcance": "INCLUIDO",
                "evidencia": "DU03P8080BL STONE PL PLT DCH 80X80 PZ BL 2 Unidad 83,20 166,40",
            },
            {
                "descripcion": "STONE PL PLT DCH 100X80 PZ BL",
                "codigo": "DU03P10080BL",
                "cantidad": "1",
                "unidad": "Unidad",
                "precio_unitario": "104.00",
                "importe": "104.00",
                "alcance": "INCLUIDO",
                "evidencia": "DU03P10080BL STONE PL PLT DCH 100X80 PZ BL 1 Unidad 104,00 104,00",
            },
            {
                "descripcion": "STONE PL PLT DCH 140X80 PZ BL",
                "codigo": "DU03P14080BL",
                "cantidad": "1",
                "unidad": "Unidad",
                "precio_unitario": "145.60",
                "importe": "145.60",
                "alcance": "INCLUIDO",
                "evidencia": "DU03P14080BL STONE PL PLT DCH 140X80 PZ BL 1 Unidad 145,60 145,60",
            },
        ],
        "condiciones_comerciales": {
            "forma_pago": "Pago por giro",
            "validez": "30 días",
            "plazo": "60 días",
            "portes": "Recogida en almacén",
            "observaciones": None,
        },
        "revision": {
            "confianza_documental": "ALTA",
            "campos_a_revisar": [],
            "advertencias": [],
        },
    }


def fake_document(text=SOURCE_TEXT):
    comparison = SimpleNamespace(team_id=7)
    bidder = SimpleNamespace(comparativa=comparison)
    offer = SimpleNamespace(pk=31, version=2, ofertante=bidder)
    return SimpleNamespace(
        pk=41,
        oferta=offer,
        texto_extraido=text,
        nombre_original="budget.pdf",
        extension=".pdf",
        content_type="application/pdf",
        datos_extraidos={
            "importacion_basica_presupuesto": {
                "method": "direct_text",
                "ocr_used": False,
                "text_len": len(text),
            }
        },
    )


def provider_result(data=None):
    return {
        "datos": deepcopy(data or valid_data()),
        "proveedor": "fake",
        "modelo": "fake-structured",
        "request_id": "req-test",
        "tokens_entrada": 100,
        "tokens_salida": 50,
        "metadata": {"store": False, "structured": True},
    }


class BudgetDocumentIntelligenceTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=5)
        self.team = SimpleNamespace(pk=7)
        self.document = fake_document()

    def analyze(self, data=None):
        requester = Mock(return_value=provider_result(data))
        result = analyze_budget_document(
            document=self.document,
            user=self.user,
            team=self.team,
            requester=requester,
        )
        return result, requester

    def test_schema_is_recursive_strict_and_versioned(self):
        self.assertEqual(BUDGET_DOCUMENT_SCHEMA_NAME, "comparativas_budget_document_v3_1")

        def assert_strict(schema):
            if schema.get("type") == "object":
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                for child in schema["properties"].values():
                    assert_strict(child)
            if schema.get("type") == "array":
                assert_strict(schema["items"])

        assert_strict(BUDGET_DOCUMENT_SCHEMA)

    def test_valid_structure_separates_supplier_customer_and_three_items(self):
        result, _ = self.analyze()
        self.assertEqual(result["preview"]["documento"]["proveedor_emisor"], "PROVEEDORA A LA INDUSTRIA Y CONSTRUCCION, S.A.")
        self.assertEqual(result["preview"]["cliente"]["nombre"], "INVERADRIDE GESTION S.L.")
        self.assertNotEqual(result["preview"]["documento"]["proveedor_emisor"], result["preview"]["cliente"]["nombre"])
        self.assertEqual(len(result["preview"]["partidas"]), 3)
        self.assertTrue(result["validation"]["valid"])

    def test_noise_labels_conditions_address_and_seller_are_not_items(self):
        result, _ = self.analyze()
        descriptions = {row["descripcion"] for row in result["preview"]["partidas"]}
        forbidden = {
            "PRECIO", "IMPORTE", "Unidad", "Forma pago", "Pago por giro",
            "Condiciones envío", "Validez de la Oferta", "Vendedor",
            "C/ DIRECCION DEL CLIENTE",
        }
        self.assertTrue(descriptions.isdisjoint(forbidden))
        instructions = build_budget_document_instructions()
        for label in forbidden - {"C/ DIRECCION DEL CLIENTE"}:
            self.assertIn(label, instructions)
        self.assertIn("INCLUIDO para una línea ofertada que contribuye", instructions)
        self.assertIn("INFORMATIVO solo para una línea real", instructions)

    def test_header_and_item_arithmetic_are_valid(self):
        result, _ = self.analyze()
        self.assertEqual(result["validation"]["economia"]["header"]["status"], "VALID")
        self.assertEqual(result["validation"]["economia"]["items_vs_base"]["status"], "VALID")
        self.assertTrue(all(row["arithmetic"]["status"] == "VALID" for row in result["validation"]["partidas"]))

    def test_review_scope_items_are_still_reconciled_without_changing_scope(self):
        data = valid_data()
        for item in data["partidas"]:
            item["alcance"] = "REVISAR"
        result, _ = self.analyze(data)
        reconciliation = result["validation"]["economia"]["items_vs_base"]
        self.assertEqual(reconciliation["status"], "VALID")
        self.assertEqual(reconciliation["sum"], "416.00")
        self.assertEqual(reconciliation["review_scope_count"], 3)
        self.assertTrue(all(item["alcance"] == "REVISAR" for item in result["preview"]["partidas"]))

    def test_economic_inconsistency_generates_review_warning_without_repair(self):
        data = valid_data()
        data["economia"]["total"] = "999.00"
        result, _ = self.analyze(data)
        self.assertEqual(result["data_ia"]["economia"]["total"], "999.00")
        self.assertEqual(result["validation"]["economia"]["header"]["status"], "REVIEW")
        self.assertEqual(result["preview"]["revision"]["confianza_documental"], "REVISAR")

    def test_missing_or_unrelated_evidence_is_rejected_and_degraded(self):
        data = valid_data()
        data["partidas"][0]["evidencia"] = ""
        with self.assertRaisesRegex(BudgetDocumentIntelligenceError, "length_invalid"):
            self.analyze(data)

        data = valid_data()
        data["partidas"][0]["evidencia"] = "EVIDENCIA INVENTADA QUE NO EXISTE"
        result, _ = self.analyze(data)
        self.assertEqual(len(result["preview"]["partidas"]), 2)
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(result["preview"]["revision"]["confianza_documental"], "REVISAR")

    def test_unknown_fields_remain_null_and_are_not_inferred(self):
        data = valid_data()
        data["documento"]["numero"] = None
        data["condiciones_comerciales"]["portes"] = None
        result, _ = self.analyze(data)
        self.assertIsNone(result["data_ia"]["documento"]["numero"])
        self.assertIsNone(result["preview"]["condiciones_comerciales"]["portes"])

    def test_requester_receives_neutral_contract_user_team_and_one_document(self):
        result, requester = self.analyze()
        kwargs = requester.call_args.kwargs
        self.assertIs(kwargs["user"], self.user)
        self.assertIs(kwargs["team"], self.team)
        self.assertEqual(kwargs["schema_name"], BUDGET_DOCUMENT_SCHEMA_NAME)
        self.assertEqual(kwargs["payload"]["document"]["document_id"], self.document.pk)
        self.assertEqual(kwargs["payload"]["document"]["offer_id"], self.document.oferta.pk)
        self.assertEqual(result["source"]["extraction"]["method"], "direct_text")

    def test_text_truncation_is_explicit_and_degrades_preview(self):
        self.document = fake_document("X" * (MAX_SOURCE_TEXT_CHARS + 7))
        data = valid_data()
        data["partidas"] = []
        result, requester = self.analyze(data)
        self.assertTrue(result["source"]["text_truncated"])
        self.assertEqual(requester.call_args.kwargs["payload"]["source"]["sent_length"], MAX_SOURCE_TEXT_CHARS)
        self.assertEqual(result["preview"]["revision"]["confianza_documental"], "REVISAR")

    def test_team_mismatch_and_empty_source_fail_before_request(self):
        requester = Mock()
        with self.assertRaisesMessage(BudgetDocumentIntelligenceError, "team_mismatch"):
            analyze_budget_document(document=self.document, user=self.user, team=SimpleNamespace(pk=8), requester=requester)
        self.assertFalse(requester.called)
        with self.assertRaisesMessage(BudgetDocumentIntelligenceError, "source_text_empty"):
            analyze_budget_document(document=fake_document(""), user=self.user, team=self.team, requester=requester)
        self.assertFalse(requester.called)

    def test_provider_failure_is_controlled(self):
        requester = Mock(side_effect=RuntimeError("network must be mocked"))
        with self.assertRaisesMessage(BudgetDocumentIntelligenceError, "provider_failed"):
            analyze_budget_document(document=self.document, user=self.user, team=self.team, requester=requester)

    def test_invalid_types_and_lengths_are_rejected_locally(self):
        data = valid_data()
        data["documento"]["proveedor_emisor"] = "X" * 501
        with self.assertRaisesRegex(BudgetDocumentIntelligenceError, "length_invalid"):
            self.analyze(data)
        data = valid_data()
        data["economia"]["base"] = {"not": "a string"}
        with self.assertRaisesRegex(BudgetDocumentIntelligenceError, "type_invalid"):
            self.analyze(data)

    def test_metadata_only_item_is_removed_from_preview(self):
        data = valid_data()
        data["partidas"].append({
            "descripcion": "PRECIO",
            "codigo": None,
            "cantidad": None,
            "unidad": None,
            "precio_unitario": None,
            "importe": None,
            "alcance": "INFORMATIVO",
            "evidencia": "PRECIO",
        })
        result, _ = self.analyze(data)
        self.assertEqual(len(result["data_ia"]["partidas"]), 4)
        self.assertEqual(len(result["preview"]["partidas"]), 3)
        self.assertFalse(result["validation"]["valid"])

    def test_module_has_no_openai_or_business_write_calls(self):
        source = Path(__file__).with_name("document_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("from intasa_ia.services import solicitar_json_estructurado", source)
        self.assertNotIn("provider_openai", source)
        self.assertNotIn("import openai", source)
        for mutation in (".save(", ".create(", ".update(", ".delete("):
            self.assertNotIn(mutation, source)
