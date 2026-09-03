import tempfile
from unittest.mock import Mock

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Team

from .document_intelligence_processing import procesar_documento_presupuesto
from .models import Comparativa, ConceptoOferta, DocumentoComparativa, Oferta, Ofertante
from .services import guardar_documento
from .test_document_intelligence import SOURCE_TEXT, provider_result


class BudgetV3ConfirmationTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.ov = override_settings(MEDIA_ROOT=self.tmp.name); self.ov.enable()
        self.user = User.objects.create_user("confirm-v3", password="x")
        self.user.user_permissions.add(Permission.objects.get(codename="access_gestion"))
        self.team = Team.objects.create(name="V3 Team"); self.user.teams.add(self.team)
        self.comp = Comparativa.objects.create(team=self.team, titulo="C", creado_por=self.user)
        self.bidder = Ofertante.objects.create(comparativa=self.comp, nombre="Original", nif="")
        self.offer = Oferta.objects.create(ofertante=self.bidder, version=1, creado_por=self.user, base="1", impuestos="0", total="1")
        self.doc, _ = guardar_documento(oferta=self.offer, uploaded_file=SimpleUploadedFile("b.txt", SOURCE_TEXT.encode(), content_type="text/plain"), user=self.user)
        self.doc.texto_extraido = SOURCE_TEXT; self.doc.save(update_fields=("texto_extraido",))
        self.scope = Team.objects.filter(pk=self.team.pk)
        self.req = Mock(return_value=provider_result())
        procesar_documento_presupuesto(self.doc.pk, user=self.user, team_scope=self.scope, requester=self.req)

    def tearDown(self): self.ov.disable(); self.tmp.cleanup()

    def test_preview_confirmation_creates_only_v3_concepts(self):
        self.client.force_login(self.user)
        self.doc.refresh_from_db()
        from .document_intelligence_confirmation import build_budget_review_initial, confirm_budget_document
        header, rows = build_budget_review_initial(self.doc)
        header.update(aceptar_advertencias=True)
        result = confirm_budget_document(self.doc.pk, user=self.user, team_scope=self.scope, header=header, reviewed_rows=rows)
        self.assertFalse(result["reused"]); self.assertEqual(ConceptoOferta.objects.filter(documento=self.doc).count(), 3)
        self.offer.refresh_from_db(); self.assertEqual(str(self.offer.total), "503.36")

    def test_confirmation_is_idempotent(self):
        from .document_intelligence_confirmation import build_budget_review_initial, confirm_budget_document
        self.doc.refresh_from_db()
        header, rows = build_budget_review_initial(self.doc); header["aceptar_advertencias"] = True
        confirm_budget_document(self.doc.pk, user=self.user, team_scope=self.scope, header=header, reviewed_rows=rows)
        again = confirm_budget_document(self.doc.pk, user=self.user, team_scope=self.scope, header=header, reviewed_rows=rows)
        self.assertTrue(again["reused"]); self.assertEqual(ConceptoOferta.objects.filter(documento=self.doc).count(), 3)

    def test_get_preview_does_not_call_ia(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("comparativas:documento_intelligence", args=[self.doc.pk]), follow=True)
        self.assertEqual(response.status_code, 200); self.assertContains(response, "Confirmar presupuesto"); self.req.assert_called_once()
