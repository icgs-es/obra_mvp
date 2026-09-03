from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.models import Team

from .models import AccesoConversacionIA, ConversacionIA, MensajeIA


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class IntasaIAResponsiveRenderTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="RESPONSIVE IA TEST")
        self.owner = User.objects.create_user(username="responsive_owner")
        self.recipient = User.objects.create_user(username="responsive_recipient")
        self.team.members.add(self.owner, self.recipient)
        permission = Permission.objects.get(
            content_type__app_label="intasa_ia",
            codename="use_intasa_ia",
        )
        self.owner.user_permissions.add(permission)
        self.recipient.user_permissions.add(permission)
        self.client.force_login(self.owner)

    def test_initial_screen_renders_mobile_controls_and_all_content(self):
        own = ConversacionIA.objects.create(
            user=self.owner,
            titulo="Conversación propia responsive",
        )
        shared = ConversacionIA.objects.create(
            user=self.recipient,
            titulo="Conversación compartida responsive",
        )
        AccesoConversacionIA.objects.create(
            conversacion=shared,
            user=self.owner,
            shared_by=self.recipient,
        )

        response = self.client.get(reverse("intasa_ia:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversaciones")
        self.assertContains(response, 'data-bs-target="#iaConversations"')
        self.assertContains(response, "offcanvas-lg offcanvas-start")
        self.assertContains(response, "bootstrap.Offcanvas.getInstance")
        self.assertContains(response, "Nueva conversación")
        self.assertContains(response, own.titulo)
        self.assertContains(response, shared.titulo)
        self.assertContains(response, "Compartidas conmigo")
        self.assertContains(response, "Búsqueda web disponible")
        self.assertContains(response, "Qué puedes preguntarle")
        self.assertContains(response, "Ver información futura")
        self.assertContains(response, "PORTAL_RESPONSIVE_GERENCIA_V1_IA")

    def test_active_conversation_preserves_messages_citations_and_sharing(self):
        conversation = ConversacionIA.objects.create(
            user=self.owner,
            titulo="Conversación activa responsive",
        )
        MensajeIA.objects.create(
            conversacion=conversation,
            rol=MensajeIA.Rol.ASISTENTE,
            contenido="Respuesta actualizada\nSegunda línea",
            metadata={
                "web_search_used": True,
                "web_citations": [{
                    "title": "Fuente meteorológica",
                    "url": "https://example.com/weather",
                }],
            },
        )

        response = self.client.get(reverse(
            "intasa_ia:detalle",
            args=[conversation.pk],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversación activa responsive")
        self.assertContains(response, "Respuesta actualizada<br>Segunda línea")
        self.assertContains(response, "Fuentes consultadas")
        self.assertContains(response, "https://example.com/weather")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "Compartir conversación")
        self.assertContains(response, 'id="iaMessages"')
        self.assertNotContains(response, "|safe")

    def test_shared_conversation_remains_read_only(self):
        conversation = ConversacionIA.objects.create(
            user=self.recipient,
            titulo="Solo lectura responsive",
        )
        AccesoConversacionIA.objects.create(
            conversacion=conversation,
            user=self.owner,
            shared_by=self.recipient,
        )

        response = self.client.get(reverse(
            "intasa_ia:detalle",
            args=[conversation.pk],
        ))

        self.assertContains(response, "Compartida contigo · solo lectura")
        self.assertNotContains(response, "Compartir conversación")
        self.assertNotContains(
            response,
            '<div class="card-footer bg-white ia-composer">',
            html=True,
        )


class IntasaIAResponsiveStaticTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).parent
        cls.template = (
            root / "templates" / "intasa_ia" / "inicio.html"
        ).read_text(encoding="utf-8")
        cls.css = (
            root / "templates" / "intasa_ia" / "_responsive.css"
        ).read_text(encoding="utf-8")

    def test_required_breakpoints_and_screen_scope_are_present(self):
        self.assertIn("@media screen and (max-width: 767.98px)", self.css)
        self.assertIn(
            "@media screen and (min-width: 768px) and (max-width: 1199.98px)",
            self.css,
        )
        self.assertIn("@media screen and (min-width: 1200px)", self.css)
        self.assertNotIn("@media print", self.css)

    def test_css_is_scoped_and_guards_horizontal_content(self):
        selectors = [
            line.strip()
            for line in self.css.splitlines()
            if line.strip().endswith("{") and not line.strip().startswith("@")
        ]
        self.assertTrue(selectors)
        self.assertTrue(all(".ia-" in selector for selector in selectors))
        self.assertIn("overflow-wrap: anywhere", self.css)
        self.assertNotIn("position: sticky", self.css)

    def test_template_security_and_desktop_grid_are_preserved(self):
        self.assertNotIn("|safe", self.template)
        self.assertIn("mensaje.contenido|linebreaksbr", self.template)
        self.assertIn('rel="noopener noreferrer"', self.template)
        self.assertIn("col-lg-4 col-xl-3", self.template)
        self.assertIn("col-lg-8 col-xl-9", self.template)
        self.assertIn("d-lg-none", self.template)
        self.assertIn("offcanvas-lg", self.template)
