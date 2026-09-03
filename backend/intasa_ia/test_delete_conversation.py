import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from actividad.models import ActividadPlataforma
from usuarios.models import Team

from .models import AccesoConversacionIA, ConversacionIA, MensajeIA


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class DeleteConversationTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="DELETE IA TEST")
        self.owner = User.objects.create_user(username="delete_owner")
        self.shared_user = User.objects.create_user(username="delete_shared")
        self.outsider = User.objects.create_user(username="delete_outsider")
        self.superuser = User.objects.create_superuser(
            username="delete_superuser",
            email="superuser@example.test",
            password="unused",
        )
        self.team.members.add(self.owner, self.shared_user, self.outsider)
        self.use_permission = Permission.objects.get(
            content_type__app_label="intasa_ia",
            codename="use_intasa_ia",
        )
        for user in (self.owner, self.shared_user, self.outsider):
            user.user_permissions.add(self.use_permission)

    def _conversation(self, *, title="Título privado eliminado"):
        conversation = ConversacionIA.objects.create(
            user=self.owner,
            team=None,
            titulo=title,
        )
        MensajeIA.objects.create(
            conversacion=conversation,
            rol=MensajeIA.Rol.USUARIO,
            contenido="Pregunta privada eliminada",
            metadata={"private": "metadata eliminada"},
        )
        MensajeIA.objects.create(
            conversacion=conversation,
            rol=MensajeIA.Rol.ASISTENTE,
            contenido="Respuesta privada eliminada",
            metadata={
                "web_citations": [{
                    "url": "https://example.com/private",
                    "title": "Fuente privada eliminada",
                }],
            },
        )
        AccesoConversacionIA.objects.create(
            conversacion=conversation,
            user=self.shared_user,
            shared_by=self.owner,
        )
        return conversation

    def _delete_url(self, conversation):
        return reverse(
            "intasa_ia:eliminar_conversacion",
            args=[conversation.pk],
        )

    @patch("intasa_ia.views.generar_respuesta_segura")
    def test_owner_post_deletes_cascades_and_redirects_without_openai(self, generate):
        conversation = self._conversation()
        conversation_id = conversation.pk
        message_ids = list(conversation.mensajes.values_list("pk", flat=True))
        access_ids = list(
            conversation.accesos_compartidos.values_list("pk", flat=True)
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            self._delete_url(conversation),
            follow=True,
        )

        self.assertRedirects(response, reverse("intasa_ia:inicio"))
        self.assertFalse(ConversacionIA.objects.filter(pk=conversation_id).exists())
        self.assertFalse(MensajeIA.objects.filter(pk__in=message_ids).exists())
        self.assertFalse(AccesoConversacionIA.objects.filter(pk__in=access_ids).exists())
        self.assertContains(response, "se ha eliminado definitivamente")
        self.assertIn(
            "La conversación se ha eliminado definitivamente.",
            [str(message) for message in get_messages(response.wsgi_request)],
        )
        generate.assert_not_called()

    def test_shared_user_cannot_delete(self):
        conversation = self._conversation()
        self.client.force_login(self.shared_user)
        response = self.client.post(self._delete_url(conversation))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_outsider_cannot_delete(self):
        conversation = self._conversation()
        self.client.force_login(self.outsider)
        response = self.client.post(self._delete_url(conversation))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_view_all_permission_does_not_allow_delete(self):
        conversation = self._conversation()
        view_all = Permission.objects.get(
            content_type__app_label="intasa_ia",
            codename="view_all_ia_conversations",
        )
        self.outsider.user_permissions.add(view_all)
        self.client.force_login(self.outsider)
        response = self.client.post(self._delete_url(conversation))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_superuser_non_owner_cannot_delete(self):
        conversation = self._conversation()
        self.client.force_login(self.superuser)
        response = self.client.post(self._delete_url(conversation))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_get_is_rejected_without_deleting(self):
        conversation = self._conversation()
        self.client.force_login(self.owner)
        response = self.client.get(self._delete_url(conversation))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_post_without_csrf_is_rejected(self):
        conversation = self._conversation()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(self._delete_url(conversation))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ConversacionIA.objects.filter(pk=conversation.pk).exists())

    def test_missing_and_second_delete_are_controlled(self):
        conversation = self._conversation()
        other = ConversacionIA.objects.create(
            user=self.owner,
            titulo="Otra conversación intacta",
        )
        url = self._delete_url(conversation)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(
            self.client.post(reverse(
                "intasa_ia:eliminar_conversacion",
                args=[999999999],
            )).status_code,
            404,
        )
        self.assertTrue(ConversacionIA.objects.filter(pk=other.pk).exists())

    def test_minimal_audit_has_counts_without_deleted_content(self):
        title = "TÍTULO_SECRETO_DELETE_TEST"
        conversation = self._conversation(title=title)
        conversation_id = conversation.pk
        ActividadPlataforma.objects.create(
            actor=self.owner,
            modulo="INTASA_IA",
            accion="CONSULTA",
            tipo_objeto=ConversacionIA._meta.label_lower,
            objeto_id=conversation_id,
            objeto_repr=f"{self.owner} · {title}",
            descripcion="Consulta privada realizada en INTASA IA.",
            metadata={},
        )
        self.client.force_login(self.owner)

        self.client.post(self._delete_url(conversation))

        audit = ActividadPlataforma.objects.get(
            modulo="INTASA_IA",
            accion="ELIMINAR",
            objeto_id=conversation_id,
        )
        self.assertEqual(audit.tipo_objeto, "intasa_ia.conversacionia")
        self.assertEqual(audit.objeto_repr, "")
        self.assertEqual(
            audit.descripcion,
            "Conversación privada de INTASA IA eliminada por su propietario.",
        )
        self.assertEqual(audit.metadata, {
            "conversation_id_deleted": conversation_id,
            "message_count_deleted": 2,
            "shared_access_count_deleted": 1,
            "permanent_delete": True,
        })
        prior = ActividadPlataforma.objects.get(accion="CONSULTA")
        self.assertEqual(prior.objeto_repr, "")
        serialized = json.dumps({
            "object_repr": audit.objeto_repr,
            "description": audit.descripcion,
            "metadata": audit.metadata,
        }, ensure_ascii=False)
        for forbidden in (
            title,
            "Pregunta privada eliminada",
            "Respuesta privada eliminada",
            "example.com/private",
            "Fuente privada eliminada",
        ):
            self.assertNotIn(forbidden, serialized)

    @patch(
        "intasa_ia.views.registrar_actividad",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_audit_failure_rolls_back_complete_delete(self, _audit):
        conversation = self._conversation()
        conversation_id = conversation.pk
        self.client.force_login(self.owner)

        with self.assertRaises(RuntimeError):
            self.client.post(self._delete_url(conversation))

        restored = ConversacionIA.objects.get(pk=conversation_id)
        self.assertEqual(restored.mensajes.count(), 2)
        self.assertEqual(restored.accesos_compartidos.count(), 1)

    def test_delete_ui_only_appears_for_owned_conversations(self):
        own = self._conversation()
        shared = ConversacionIA.objects.create(
            user=self.shared_user,
            titulo="Compartida sin papelera",
        )
        AccesoConversacionIA.objects.create(
            conversacion=shared,
            user=self.owner,
            shared_by=self.shared_user,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("intasa_ia:inicio"))
        content = response.content.decode("utf-8")

        self.assertContains(response, self._delete_url(own))
        self.assertNotIn(self._delete_url(shared), content)
        self.assertContains(response, 'id="iaDeleteConversationModal"')
        self.assertContains(response, "Eliminar definitivamente")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'id="iaConversations"')
        self.assertNotIn("|safe", content)
