from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from intasa_ia import help_bridge
from intasa_ia.models import (
    ConversacionIA,
    MensajeIA,
)


class IntasaIAHelpBridgeV1Tests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username="ia-help-user",
                password="test-password",
            )
        )

        self.conversation = (
            ConversacionIA.objects.create(
                user=self.user,
                titulo="Consulta de ayuda",
            )
        )

    def _grant_gestion(self):
        permission = Permission.objects.get(
            content_type__app_label=(
                "gestion"
            ),
            codename="access_gestion",
        )

        self.user.user_permissions.add(
            permission
        )

        self.user = (
            get_user_model()
            .objects
            .get(pk=self.user.pk)
        )

        self.conversation.user = self.user

    def _add_question(
        self,
        content,
    ):
        MensajeIA.objects.create(
            conversacion=self.conversation,
            rol=MensajeIA.Rol.USUARIO,
            contenido=content,
        )

    @staticmethod
    def _fake_openai_result():
        return {
            "contenido": "Respuesta generada.",
            "proveedor": "openai",
            "modelo": "test-model",
            "request_id": "test-request",
            "tokens_entrada": 10,
            "tokens_salida": 20,
            "metadata": {},
        }

    def test_help_context_is_added_to_transcript(
        self,
    ):
        self._grant_gestion()

        question = (
            "¿Cómo autorizo un plan de pagos?"
        )

        self._add_question(
            question
        )

        def fake_core(
            *,
            conversacion,
            pregunta,
            user,
        ):
            self.assertEqual(
                pregunta,
                question,
            )

            transcript = (
                help_bridge
                ._core_services
                ._crear_transcripcion(
                    conversacion
                )
            )

            return {
                **self._fake_openai_result(),
                "contenido": transcript,
            }

        with patch(
            "intasa_ia.help_bridge."
            "_core_services."
            "generar_respuesta_segura",
            side_effect=fake_core,
        ):
            result = (
                help_bridge
                .generar_respuesta_segura(
                    conversacion=(
                        self.conversation
                    ),
                    pregunta=question,
                    user=self.user,
                )
            )

        self.assertIn(
            "DOCUMENTACIÓN INTERNA AUTORIZADA",
            result["contenido"],
        )

        self.assertIn(
            "Planes de pago y vencimientos",
            result["contenido"],
        )

        metadata = result["metadata"]

        self.assertTrue(
            metadata[
                "ayuda_interna_consultada"
            ]
        )

    def test_user_without_permission_does_not_receive_facturation(
        self,
    ):
        question = (
            "¿Cómo autorizo un plan de pagos?"
        )

        self._add_question(
            question
        )

        def fake_core(
            *,
            conversacion,
            pregunta,
            user,
        ):
            transcript = (
                help_bridge
                ._core_services
                ._crear_transcripcion(
                    conversacion
                )
            )

            return {
                **self._fake_openai_result(),
                "contenido": transcript,
            }

        with patch(
            "intasa_ia.help_bridge."
            "_core_services."
            "generar_respuesta_segura",
            side_effect=fake_core,
        ):
            result = (
                help_bridge
                .generar_respuesta_segura(
                    conversacion=(
                        self.conversation
                    ),
                    pregunta=question,
                    user=self.user,
                )
            )

        self.assertNotIn(
            "Planes de pago y vencimientos",
            result["contenido"],
        )

    def test_openai_answer_receives_source_footer(
        self,
    ):
        self._grant_gestion()

        question = (
            "¿Qué significa AUT. PAGO?"
        )

        self._add_question(
            question
        )

        with patch(
            "intasa_ia.help_bridge."
            "_core_services."
            "generar_respuesta_segura",
            return_value=(
                self._fake_openai_result()
            ),
        ):
            result = (
                help_bridge
                .generar_respuesta_segura(
                    conversacion=(
                        self.conversation
                    ),
                    pregunta=question,
                    user=self.user,
                )
            )

        self.assertIn(
            "Fuentes internas consultadas:",
            result["contenido"],
        )

        self.assertTrue(
            result["metadata"][
                "ayuda_interna_consultada"
            ]
        )

    def test_local_safe_uses_internal_help(
        self,
    ):
        self._grant_gestion()

        question = (
            "¿Cómo registro un vencimiento "
            "como pagado?"
        )

        self._add_question(
            question
        )

        local_result = {
            "contenido": (
                "INTASA IA está instalada "
                "en modo local."
            ),
            "proveedor": "local-safe",
            "modelo": "",
            "request_id": "",
            "tokens_entrada": None,
            "tokens_salida": None,
            "metadata": {},
        }

        with patch(
            "intasa_ia.help_bridge."
            "_core_services."
            "generar_respuesta_segura",
            return_value=local_result,
        ):
            result = (
                help_bridge
                .generar_respuesta_segura(
                    conversacion=(
                        self.conversation
                    ),
                    pregunta=question,
                    user=self.user,
                )
            )

        self.assertEqual(
            result["proveedor"],
            "local-help",
        )

        self.assertEqual(
            result["modelo"],
            "ayuda-interna-v1",
        )

        self.assertIn(
            "Registrar un vencimiento como pagado",
            result["contenido"],
        )

        self.assertTrue(
            result["metadata"][
                "ayuda_interna_consultada"
            ]
        )
