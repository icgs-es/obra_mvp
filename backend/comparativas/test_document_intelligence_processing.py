import hashlib
from pathlib import Path
import re
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Team

from .document_intelligence_processing import (
    DOCUMENT_INTELLIGENCE_NAMESPACE,
    BudgetDocumentProcessingError,
    DocumentTextResult,
    procesar_documento_presupuesto,
)
from .models import Comparativa, ConceptoOferta, DocumentoComparativa, Oferta, Ofertante
from .services import guardar_documento
from .test_document_intelligence import SOURCE_TEXT, provider_result


class DocumentIntelligenceProcessingTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.settings_override.enable()
        self.user = User.objects.create_user("v3-slice2", password="test")
        self.team = Team.objects.create(name="Empresa Slice 2")
        self.user.teams.add(self.team)
        permission = Permission.objects.get(
            codename="access_gestion",
            content_type__app_label="gestion",
        )
        self.user.user_permissions.add(permission)
        self.comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Preview V3",
            creado_por=self.user,
        )
        self.ofertante = Ofertante.objects.create(
            comparativa=self.comparativa,
            nombre="Proveedor original",
            nif="B00000001",
        )
        self.oferta = Oferta.objects.create(
            ofertante=self.ofertante,
            version=1,
            referencia="REF-ORIGINAL",
            base="10.00",
            impuestos="2.10",
            total="12.10",
            creado_por=self.user,
        )
        self.documento, _ = guardar_documento(
            oferta=self.oferta,
            uploaded_file=SimpleUploadedFile(
                "budget.txt",
                SOURCE_TEXT.encode("utf-8"),
                content_type="text/plain",
            ),
            user=self.user,
        )
        self.documento.texto_extraido = SOURCE_TEXT
        self.documento.datos_extraidos = {
            "legacy_namespace": {"preserved": True},
            "conceptos_v2c": {"status": "historic"},
        }
        self.documento.save(update_fields=("texto_extraido", "datos_extraidos"))
        self.team_scope = Team.objects.filter(pk=self.team.pk)
        self.requester = Mock(return_value=provider_result())
        self.client.force_login(self.user)
        session = self.client.session
        session["active_team_id"] = str(self.team.pk)
        session.save()

    def tearDown(self):
        self.settings_override.disable()
        self.temp_media.cleanup()

    def process(self, **kwargs):
        return procesar_documento_presupuesto(
            self.documento.pk,
            user=self.user,
            team_scope=self.team_scope,
            requester=kwargs.pop("requester", self.requester),
            **kwargs,
        )

    def business_snapshot(self):
        return {
            "comparativa": Comparativa.objects.filter(pk=self.comparativa.pk).values().get(),
            "ofertante": Ofertante.objects.filter(pk=self.ofertante.pk).values().get(),
            "oferta": Oferta.objects.filter(pk=self.oferta.pk).values().get(),
            "conceptos": list(
                ConceptoOferta.objects.filter(oferta=self.oferta).values().order_by("pk")
            ),
        }

    def test_existing_text_is_used_and_preview_is_persisted(self):
        result = self.process()
        self.documento.refresh_from_db()
        namespace = self.documento.datos_extraidos[DOCUMENT_INTELLIGENCE_NAMESPACE]
        self.assertEqual(result["status"], "COMPLETADO")
        self.assertEqual(namespace["source"]["text_method"], "stored_text")
        self.assertEqual(namespace["preview"]["economia"]["total"], "503.36")
        self.assertEqual(self.documento.texto_extraido, SOURCE_TEXT)

    def test_empty_text_uses_injected_neutral_extractor(self):
        self.documento.texto_extraido = ""
        self.documento.save(update_fields=("texto_extraido",))
        extractor = Mock(return_value=DocumentTextResult(
            text=SOURCE_TEXT,
            method="fake-neutral",
            pages=2,
            sheets=None,
            ocr_used=True,
            truncated=False,
            extractor_version="fake-v1",
        ))
        self.process(extractor=extractor)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.texto_extraido, SOURCE_TEXT)
        source = self.documento.datos_extraidos[DOCUMENT_INTELLIGENCE_NAMESPACE]["source"]
        self.assertEqual(source["text_method"], "fake-neutral")
        self.assertEqual(source["pages"], 2)
        self.assertTrue(source["ocr_used"])

    def test_empty_text_uses_real_neutral_text_extractor(self):
        self.documento.texto_extraido = ""
        self.documento.save(update_fields=("texto_extraido",))
        self.process()
        self.documento.refresh_from_db()
        source = self.documento.datos_extraidos[DOCUMENT_INTELLIGENCE_NAMESPACE]["source"]
        self.assertEqual(self.documento.texto_extraido, SOURCE_TEXT)
        self.assertTrue(source["text_method"].startswith("text:"))
        self.assertFalse(source["ocr_used"])

    def test_only_v3_namespace_changes_and_historic_namespaces_survive(self):
        self.process()
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.datos_extraidos["legacy_namespace"], {"preserved": True})
        self.assertEqual(self.documento.datos_extraidos["conceptos_v2c"], {"status": "historic"})
        self.assertIn(DOCUMENT_INTELLIGENCE_NAMESPACE, self.documento.datos_extraidos)

    def test_business_models_and_concepts_are_unchanged(self):
        ConceptoOferta.objects.create(
            oferta=self.oferta,
            documento=self.documento,
            orden=1,
            titulo_original="Concepto confirmado",
            cantidad="1",
        )
        before = self.business_snapshot()
        self.process()
        self.assertEqual(before, self.business_snapshot())

    def test_get_never_calls_provider_and_renders_pending_action(self):
        url = reverse("comparativas:documento_intelligence", args=(self.documento.pk,))
        with patch("comparativas.document_intelligence.solicitar_json_estructurado") as provider:
            response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analizar con INTASA IA")
        provider.assert_not_called()

    def test_post_analyze_calls_provider_and_renders_preview(self):
        url = reverse("comparativas:documento_intelligence", args=(self.documento.pk,))
        with patch(
            "comparativas.document_intelligence.solicitar_json_estructurado",
            return_value=provider_result(),
        ) as provider:
            response = self.client.post(url, {"action": "analyze"}, follow=True, secure=True)
        self.assertEqual(response.status_code, 200)
        provider.assert_called_once()
        self.assertContains(response, "PROVEEDORA A LA INDUSTRIA")
        self.assertContains(response, "DU03P8080BL")
        self.assertContains(response, "Validación aritmética")

    def test_same_fingerprint_reuses_without_extractor_or_provider(self):
        first = self.process()
        second_provider = Mock(side_effect=AssertionError("provider must not run"))
        second_extractor = Mock(side_effect=AssertionError("extractor must not run"))
        second = self.process(requester=second_provider, extractor=second_extractor)
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        second_provider.assert_not_called()
        second_extractor.assert_not_called()

    def test_reanalyze_forces_provider_and_keeps_compact_history(self):
        self.process()
        forced = Mock(return_value=provider_result())
        result = self.process(requester=forced, force=True)
        forced.assert_called_once()
        self.assertFalse(result["reused"])
        self.documento.refresh_from_db()
        history = self.documento.datos_extraidos[DOCUMENT_INTELLIGENCE_NAMESPACE]["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "COMPLETADO")
        self.assertNotIn("preview", history[0])
        self.assertNotIn("data_ia", history[0])

    def test_provider_failure_sets_safe_error_without_business_write(self):
        before = self.business_snapshot()
        with self.assertRaisesRegex(BudgetDocumentProcessingError, "provider_failed"):
            self.process(requester=Mock(side_effect=RuntimeError("secret provider detail")))
        self.documento.refresh_from_db()
        namespace = self.documento.datos_extraidos[DOCUMENT_INTELLIGENCE_NAMESPACE]
        self.assertEqual(namespace["status"], "ERROR")
        self.assertEqual(namespace["error"], "provider_failed")
        self.assertNotIn("secret", self.documento.error_analisis)
        self.assertEqual(before, self.business_snapshot())

    def test_extractor_failure_sets_error_and_does_not_call_provider(self):
        self.documento.texto_extraido = ""
        self.documento.save(update_fields=("texto_extraido",))
        provider = Mock()
        extractor = Mock(side_effect=BudgetDocumentProcessingError("extractor_failed"))
        with self.assertRaisesRegex(BudgetDocumentProcessingError, "extractor_failed"):
            self.process(requester=provider, extractor=extractor)
        provider.assert_not_called()
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado_analisis, DocumentoComparativa.EstadoAnalisis.ERROR)

    def test_other_team_document_is_404_and_preview_is_not_disclosed(self):
        other_team = Team.objects.create(name="Empresa ajena Slice 2")
        other_comparison = Comparativa.objects.create(team=other_team, titulo="Oculta")
        other_bidder = Ofertante.objects.create(comparativa=other_comparison, nombre="Oculto")
        other_offer = Oferta.objects.create(ofertante=other_bidder, version=1)
        other_doc, _ = guardar_documento(
            oferta=other_offer,
            uploaded_file=SimpleUploadedFile("hidden.txt", SOURCE_TEXT.encode()),
            user=self.user,
        )
        response = self.client.get(
            reverse("comparativas:documento_intelligence", args=(other_doc.pk,)),
            secure=True,
        )
        self.assertEqual(response.status_code, 404)
        with self.assertRaises(Http404):
            # Http404 deliberadamente no revela si el documento existe.
            procesar_documento_presupuesto(
                other_doc.pk,
                user=self.user,
                team_scope=self.team_scope,
                requester=self.requester,
            )

    def test_user_without_functional_permission_is_rejected(self):
        outsider = User.objects.create_user("v3-no-permission")
        outsider.teams.add(self.team)
        self.client.force_login(outsider)
        session = self.client.session
        session["active_team_id"] = str(self.team.pk)
        session.save()
        response = self.client.get(
            reverse("comparativas:documento_intelligence", args=(self.documento.pk,)),
            secure=True,
        )
        self.assertEqual(response.status_code, 403)

    def test_template_shows_evidence_warnings_and_validation(self):
        self.process()
        response = self.client.get(
            reverse("comparativas:documento_intelligence", args=(self.documento.pk,)),
            secure=True,
        )
        self.assertContains(response, "Evidencia")
        self.assertContains(response, "Revisión")
        self.assertContains(response, "VALID")
        self.assertContains(response, "Pago por giro")

    def test_csrf_is_required_for_mutating_action(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        session = client.session
        session["active_team_id"] = str(self.team.pk)
        session.save()
        response = client.post(
            reverse("comparativas:documento_intelligence", args=(self.documento.pk,)),
            {"action": "analyze"},
            secure=True,
        )
        self.assertEqual(response.status_code, 403)
        self.documento.refresh_from_db()
        self.assertNotIn(DOCUMENT_INTELLIGENCE_NAMESPACE, self.documento.datos_extraidos)

    def test_invalid_post_action_does_not_call_provider(self):
        url = reverse("comparativas:documento_intelligence", args=(self.documento.pk,))
        with patch("comparativas.document_intelligence.solicitar_json_estructurado") as provider:
            response = self.client.post(url, {"action": "invalid"}, follow=True, secure=True)
        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()

    def test_detail_exposes_explicit_v3_action_after_upload(self):
        response = self.client.get(
            reverse("comparativas:detail", args=(self.comparativa.uuid,)),
            secure=True,
        )
        self.assertContains(response, "Analizar con INTASA IA")
        self.assertContains(
            response,
            reverse("comparativas:documento_intelligence", args=(self.documento.pk,)),
        )

    def test_duplicate_offer_versions_do_not_mix_documents(self):
        second_offer = Oferta.objects.create(ofertante=self.ofertante, version=2)
        second_doc, _ = guardar_documento(
            oferta=second_offer,
            uploaded_file=SimpleUploadedFile("second.txt", b"other version"),
            user=self.user,
        )
        self.process()
        second_doc.refresh_from_db()
        self.assertNotIn(DOCUMENT_INTELLIGENCE_NAMESPACE, second_doc.datos_extraidos)
        self.assertEqual(second_doc.estado_analisis, DocumentoComparativa.EstadoAnalisis.PENDIENTE)

    def test_offer_economic_fields_are_not_persisted_from_preview(self):
        self.process()
        self.oferta.refresh_from_db()
        self.assertEqual(str(self.oferta.base), "10.00")
        self.assertEqual(str(self.oferta.impuestos), "2.10")
        self.assertEqual(str(self.oferta.total), "12.10")
        self.assertEqual(self.oferta.referencia, "REF-ORIGINAL")

    def test_sha_mismatch_fails_closed_before_provider(self):
        self.documento.sha256 = hashlib.sha256(b"different").hexdigest()
        self.documento.save(update_fields=("sha256",))
        with self.assertRaisesRegex(BudgetDocumentProcessingError, "document_sha256_mismatch"):
            self.process()
        self.requester.assert_not_called()

    def test_no_comparativas_module_imports_openai_directly(self):
        root = Path(__file__).resolve().parent
        offenders = []
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*(?:from\s+openai|import\s+openai)\b", text, re.MULTILINE):
                offenders.append(path.name)
        self.assertEqual(offenders, [])
