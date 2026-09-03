from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from usuarios.models import Team

from .models import (
    AccesoConversacionIA,
    ConversacionIA,
    MensajeIA,
)
from .provider_openai import (
    IAProviderError,
    solicitar_respuesta_openai,
)


User = get_user_model()


RESULTADO_OK = {
    "contenido": "Respuesta de prueba.",
    "proveedor": "openai",
    "modelo": "gpt-5-mini-2025-08-07",
    "request_id": "req_test",
    "tokens_entrada": 20,
    "tokens_salida": 10,
    "metadata": {
        "external_call": True,
        "read_only": True,
        "store": False,
    },
}


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class IntasaIAV1CTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(
            name="EMPRESA IA TEST"
        )

        self.owner = User.objects.create_user(
            username="ia_owner",
            password="test12345",
        )

        self.recipient = User.objects.create_user(
            username="ia_recipient",
            password="test12345",
        )

        self.outsider = User.objects.create_user(
            username="ia_outsider",
            password="test12345",
        )

        self.team.members.add(
            self.owner,
            self.recipient,
        )

        self.permission = Permission.objects.get(
            content_type__app_label="intasa_ia",
            codename="use_intasa_ia",
        )

        self.owner.user_permissions.add(
            self.permission
        )

        self.recipient.user_permissions.add(
            self.permission
        )

        self.outsider.user_permissions.add(
            self.permission
        )

    def _conversation(self):
        return ConversacionIA.objects.create(
            user=self.owner,
            team=None,
            titulo="Idea compartida",
        )

    def test_inicio_muestra_privacidad_y_sugerencias(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("intasa_ia:inicio")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Privado por usuario",
        )

        self.assertContains(
            response,
            "¿Cuántos leads entraron esta semana?",
        )

        self.assertContains(
            response,
            "¿Cuánto tiene que pagar la empresa este mes?",
        )

    @patch(
        "intasa_ia.views.generar_respuesta_segura",
        return_value=RESULTADO_OK,
    )
    def test_crear_conversacion_no_exige_empresa(
        self,
        mock_generate,
    ):
        self.client.force_login(self.owner)

        session = self.client.session
        session["active_team_id"] = "all"
        session.save()

        response = self.client.post(
            reverse("intasa_ia:inicio"),
            {
                "pregunta": (
                    "Ayúdame a preparar un proyecto."
                )
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        conversation = ConversacionIA.objects.get()

        self.assertIsNone(
            conversation.team,
        )

        self.assertEqual(
            conversation.user,
            self.owner,
        )

        self.assertEqual(
            conversation.mensajes.count(),
            2,
        )

        mock_generate.assert_called_once()

    def test_compartir_con_usuario_autorizado(self):
        conversation = self._conversation()

        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "intasa_ia:compartir",
                args=[conversation.pk],
            ),
            {
                "usuario": self.recipient.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            AccesoConversacionIA.objects.filter(
                conversacion=conversation,
                user=self.recipient,
                shared_by=self.owner,
            ).exists()
        )

    def test_destinatario_ve_conversacion_compartida(self):
        conversation = self._conversation()

        AccesoConversacionIA.objects.create(
            conversacion=conversation,
            user=self.recipient,
            shared_by=self.owner,
        )

        self.client.force_login(self.recipient)

        response = self.client.get(
            reverse(
                "intasa_ia:detalle",
                args=[conversation.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Compartida contigo",
        )

        self.assertContains(
            response,
            "solo lectura",
        )

    def test_destinatario_no_puede_escribir(self):
        conversation = self._conversation()

        AccesoConversacionIA.objects.create(
            conversacion=conversation,
            user=self.recipient,
            shared_by=self.owner,
        )

        self.client.force_login(self.recipient)

        response = self.client.post(
            reverse(
                "intasa_ia:detalle",
                args=[conversation.pk],
            ),
            {
                "pregunta": "Intento de escritura",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertEqual(
            conversation.mensajes.count(),
            0,
        )

    def test_usuario_no_autorizado_recibe_404(self):
        conversation = self._conversation()

        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse(
                "intasa_ia:detalle",
                args=[conversation.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_retirar_acceso_compartido(self):
        conversation = self._conversation()

        AccesoConversacionIA.objects.create(
            conversacion=conversation,
            user=self.recipient,
            shared_by=self.owner,
        )

        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "intasa_ia:retirar_compartido",
                args=[
                    conversation.pk,
                    self.recipient.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            AccesoConversacionIA.objects.filter(
                conversacion=conversation,
                user=self.recipient,
            ).exists()
        )

    def test_usuario_sin_permiso_recibe_403(self):
        no_permission = User.objects.create_user(
            username="without_permission",
            password="test12345",
        )

        self.client.force_login(no_permission)

        response = self.client.get(
            reverse("intasa_ia:inicio")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    @patch(
        "intasa_ia.views.generar_respuesta_segura",
        side_effect=IAProviderError(
            "timeout",
            request_id="req_timeout",
        ),
    )
    def test_error_proveedor_no_pierde_consulta(
        self,
        mock_generate,
    ):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("intasa_ia:inicio"),
            {
                "pregunta": "Pregunta con timeout",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        conversation = ConversacionIA.objects.get()

        self.assertEqual(
            conversation.mensajes.count(),
            2,
        )

        assistant = conversation.mensajes.last()

        self.assertEqual(
            assistant.proveedor,
            "openai-error",
        )


class OpenAIProviderTests(TestCase):
    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_responses_api_store_false(
        self,
        mock_post,
    ):
        response = Mock()
        response.status_code = 200
        response.headers = {
            "x-request-id": "req_provider_test",
        }
        response.json.return_value = {
            "id": "resp_test",
            "status": "completed",
            "model": "gpt-5-mini-2025-08-07",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Respuesta correcta",
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 15,
                "output_tokens": 7,
                "total_tokens": 22,
            },
        }

        mock_post.return_value = response

        result = solicitar_respuesta_openai(
            config={
                "api_key": "test-key",
                "model": "gpt-5-mini-2025-08-07",
                "base_url": "https://api.openai.com/v1",
                "timeout_seconds": 45,
                "max_output_tokens": 1200,
                "store": False,
            },
            transcript="Usuario: Hola",
            instructions="Responde en español.",
            safety_identifier="hashed-user",
            metadata={
                "application": "intasa_ia",
            },
        )

        payload = mock_post.call_args.kwargs[
            "json"
        ]

        self.assertIs(
            payload["store"],
            False,
        )

        self.assertEqual(
            result["contenido"],
            "Respuesta correcta",
        )

    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_rate_limit_controlado(
        self,
        mock_post,
    ):
        response = Mock()
        response.status_code = 429
        response.headers = {
            "x-request-id": "req_rate",
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_respuesta_openai(
                config={
                    "api_key": "test-key",
                    "model": "gpt-5-mini",
                    "base_url": (
                        "https://api.openai.com/v1"
                    ),
                    "timeout_seconds": 45,
                    "max_output_tokens": 1200,
                    "store": False,
                },
                transcript="Usuario: Hola",
                instructions="Responde.",
                safety_identifier="hash",
                metadata={},
            )

        self.assertEqual(
            context.exception.code,
            "rate_limit",
        )


# INTASA_IA_STRUCTURED_JSON_V1_TESTS

from django.test import (
    TestCase as
    StructuredJSONTestCase,
)
from unittest.mock import (
    Mock as StructuredMock,
    patch as structured_patch,
)


class StructuredJSONProviderTests(
    StructuredJSONTestCase
):

    @structured_patch(
        (
            "intasa_ia."
            "provider_openai."
            "requests.post"
        )
    )
    def test_structured_responses_uses_json_schema_strict(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            solicitar_json_estructurado_openai,
        )

        response = (
            StructuredMock()
        )

        response.status_code = 200

        response.headers = {
            "x-request-id": (
                "req_structured"
            ),
        }

        response.json.return_value = {
            "id": "resp_structured",
            "status": "completed",
            "model": (
                "gpt-5-mini-"
                "2025-08-07"
            ),
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": (
                                "output_text"
                            ),
                            "text": (
                                '{"groups":[]}'
                            ),
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 40,
                "output_tokens": 8,
                "total_tokens": 48,
            },
        }

        mock_post.return_value = (
            response
        )

        schema = {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {
                        "type": (
                            "object"
                        ),
                        "properties": {},
                        "additionalProperties": (
                            False
                        ),
                    },
                }
            },
            "required": [
                "groups"
            ],
            "additionalProperties": (
                False
            ),
        }

        result = (
            solicitar_json_estructurado_openai(
                config={
                    "api_key": "test-key",
                    "model": (
                        "gpt-5-mini-"
                        "2025-08-07"
                    ),
                    "base_url": (
                        "https://api."
                        "openai.com/v1"
                    ),
                    "timeout_seconds": (
                        45
                    ),
                    "max_output_tokens": (
                        1200
                    ),
                    "store": False,
                },
                input_payload={
                    "units": [],
                },
                instructions=(
                    "Devuelve grupos."
                ),
                schema_name=(
                    "comparativa_matching"
                ),
                schema=schema,
                safety_identifier=(
                    "hashed-user"
                ),
                metadata={
                    "application": (
                        "intasa_ia"
                    ),
                },
            )
        )

        request_payload = (
            mock_post
            .call_args
            .kwargs["json"]
        )

        self.assertFalse(
            request_payload["store"]
        )

        self.assertEqual(
            request_payload[
                "text"
            ][
                "format"
            ][
                "type"
            ],
            "json_schema",
        )

        self.assertEqual(
            request_payload[
                "text"
            ][
                "format"
            ][
                "name"
            ],
            "comparativa_matching",
        )

        self.assertTrue(
            request_payload[
                "text"
            ][
                "format"
            ][
                "strict"
            ]
        )

        self.assertEqual(
            request_payload[
                "text"
            ][
                "format"
            ][
                "schema"
            ],
            schema,
        )

        self.assertEqual(
            request_payload[
                "reasoning"
            ],
            {
                "effort": "low",
            },
        )

        self.assertEqual(
            result["datos"],
            {
                "groups": [],
            },
        )

        self.assertTrue(
            result[
                "metadata"
            ][
                "structured"
            ]
        )

        self.assertTrue(
            result[
                "metadata"
            ][
                "strict"
            ]
        )


    @structured_patch(
        (
            "intasa_ia."
            "provider_openai."
            "requests.post"
        )
    )
    def test_structured_invalid_output_json_is_controlled(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = (
            StructuredMock()
        )

        response.status_code = 200
        response.headers = {}

        response.json.return_value = {
            "id": "resp_bad",
            "status": "completed",
            "model": "gpt-5-mini",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": (
                                "output_text"
                            ),
                            "text": (
                                "not-json"
                            ),
                        }
                    ],
                }
            ],
        }

        mock_post.return_value = (
            response
        )

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                config={
                    "api_key": "key",
                    "model": (
                        "gpt-5-mini"
                    ),
                    "base_url": (
                        "https://api."
                        "openai.com/v1"
                    ),
                    "timeout_seconds": 45,
                    "max_output_tokens": 1200,
                    "store": False,
                },
                input_payload={},
                instructions="Test",
                schema_name="test_schema",
                schema={
                    "type": "object",
                },
                safety_identifier="hash",
                metadata={},
            )

        self.assertEqual(
            context.exception.code,
            "structured_invalid_json",
        )


    def test_structured_rejects_invalid_schema_name_without_network(
        self,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                config={
                    "api_key": "key",
                    "model": (
                        "gpt-5-mini"
                    ),
                    "base_url": (
                        "https://api."
                        "openai.com/v1"
                    ),
                    "timeout_seconds": 45,
                    "max_output_tokens": 1200,
                    "store": False,
                },
                input_payload={},
                instructions="Test",
                schema_name=(
                    "nombre no valido"
                ),
                schema={
                    "type": "object",
                },
                safety_identifier="hash",
                metadata={},
            )

        self.assertEqual(
            context.exception.code,
            (
                "structured_"
                "schema_name_invalid"
            ),
        )


    @structured_patch(
        (
            "intasa_ia.services."
            "_solicitar_json_estructurado_openai"
        )
    )
    @structured_patch(
        (
            "intasa_ia.services."
            "cargar_config_openai"
        )
    )
    @structured_patch(
        (
            "intasa_ia.services."
            "obtener_estado_proveedor"
        )
    )
    def test_public_structured_service_hides_provider_details(
        self,
        mock_estado,
        mock_config,
        mock_provider,
    ):
        from types import (
            SimpleNamespace,
        )

        from intasa_ia.services import (
            solicitar_json_estructurado,
        )

        mock_estado.return_value = {
            "enabled": True,
            "configured": True,
            "model": (
                "gpt-5-mini-"
                "2025-08-07"
            ),
            "error": "",
        }

        mock_config.return_value = {
            "api_key": "secret",
            "model": (
                "gpt-5-mini-"
                "2025-08-07"
            ),
            "base_url": (
                "https://api."
                "openai.com/v1"
            ),
            "timeout_seconds": 45,
            "max_output_tokens": 1200,
            "store": False,
        }

        mock_provider.return_value = {
            "datos": {
                "groups": [],
            },
            "proveedor": "openai",
        }

        user = SimpleNamespace(
            pk=123,
        )

        team = SimpleNamespace(
            pk=456,
        )

        result = (
            solicitar_json_estructurado(
                instructions=(
                    "Agrupa conceptos."
                ),
                payload={
                    "units": [],
                },
                schema_name=(
                    "comparativa_matching"
                ),
                schema={
                    "type": "object",
                },
                user=user,
                team=team,
                metadata={
                    "case_id": "abc",
                },
            )
        )

        self.assertEqual(
            result[
                "datos"
            ],
            {
                "groups": [],
            },
        )

        kwargs = (
            mock_provider
            .call_args
            .kwargs
        )

        self.assertEqual(
            kwargs[
                "metadata"
            ][
                "application"
            ],
            "intasa_ia",
        )

        self.assertEqual(
            kwargs[
                "metadata"
            ][
                "task"
            ],
            "structured_json",
        )

        self.assertEqual(
            kwargs[
                "metadata"
            ][
                "team_id"
            ],
            456,
        )

        self.assertEqual(
            kwargs[
                "metadata"
            ][
                "case_id"
            ],
            "abc",
        )

        self.assertNotIn(
            "api_key",
            kwargs,
        )


    @structured_patch(
        (
            "intasa_ia.services."
            "obtener_estado_proveedor"
        )
    )
    def test_public_structured_service_rejects_disabled_provider(
        self,
        mock_estado,
    ):
        from types import (
            SimpleNamespace,
        )

        from intasa_ia.provider_openai import (
            IAProviderError,
        )
        from intasa_ia.services import (
            solicitar_json_estructurado,
        )

        mock_estado.return_value = {
            "enabled": False,
            "configured": True,
            "model": "gpt-5-mini",
            "error": "",
        }

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado(
                instructions="Test",
                payload={},
                schema_name="test_schema",
                schema={
                    "type": "object",
                },
                user=SimpleNamespace(
                    pk=1
                ),
            )

        self.assertEqual(
            context.exception.code,
            "provider_disabled",
        )


# INTASA_IA_STRUCTURED_RESPONSE_HARDENING_V1

class StructuredResponseClassificationTests(
    TestCase
):
    def _config(self):
        return {
            "api_key": "test-key",
            "model": (
                "gpt-5-mini-"
                "2025-08-07"
            ),
            "base_url": (
                "https://api.openai.com/v1"
            ),
            "timeout_seconds": 45,
            "max_output_tokens": 1200,
            "store": False,
        }

    def _kwargs(self):
        return {
            "config": self._config(),
            "input_payload": {
                "source_units": [],
            },
            "instructions": "Test.",
            "schema_name": (
                "structured_test"
            ),
            "schema": {
                "type": "object",
            },
            "safety_identifier": (
                "hashed-user"
            ),
            "metadata": {},
        }

    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_structured_incomplete_is_not_reported_as_invalid_json(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = Mock()
        response.status_code = 200
        response.headers = {
            "x-request-id": (
                "req_incomplete"
            ),
        }

        response.json.return_value = {
            "id": "resp_incomplete",
            "status": "incomplete",
            "incomplete_details": {
                "reason": "max_output_tokens",
            },
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                '{"groups":['
                            ),
                        }
                    ],
                }
            ],
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                **self._kwargs()
            )

        self.assertEqual(
            context.exception.code,
            (
                "structured_incomplete_"
                "max_output_tokens"
            ),
        )

        self.assertEqual(
            context.exception.request_id,
            "req_incomplete",
        )

        self.assertEqual(
            context.exception.http_status,
            200,
        )


    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_structured_incomplete_accepts_max_tokens_reason(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = Mock()
        response.status_code = 200
        response.headers = {}

        response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {
                "reason": "max_tokens",
            },
            "output": [],
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                **self._kwargs()
            )

        self.assertEqual(
            context.exception.code,
            (
                "structured_incomplete_"
                "max_tokens"
            ),
        )


    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_structured_refusal_is_classified_before_json_parse(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = Mock()
        response.status_code = 200
        response.headers = {
            "x-request-id": (
                "req_refusal"
            ),
        }

        response.json.return_value = {
            "id": "resp_refusal",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "refusal",
                            "refusal": (
                                "No puedo responder."
                            ),
                        }
                    ],
                }
            ],
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                **self._kwargs()
            )

        self.assertEqual(
            context.exception.code,
            "structured_refusal",
        )

        self.assertEqual(
            context.exception.request_id,
            "req_refusal",
        )


    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_structured_completed_malformed_json_remains_invalid_json(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = Mock()
        response.status_code = 200
        response.headers = {}

        response.json.return_value = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "not-json",
                        }
                    ],
                }
            ],
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                **self._kwargs()
            )

        self.assertEqual(
            context.exception.code,
            "structured_invalid_json",
        )


    @patch(
        "intasa_ia.provider_openai.requests.post"
    )
    def test_structured_noncompleted_terminal_status_is_classified(
        self,
        mock_post,
    ):
        from intasa_ia.provider_openai import (
            IAProviderError,
            solicitar_json_estructurado_openai,
        )

        response = Mock()
        response.status_code = 200
        response.headers = {}

        response.json.return_value = {
            "status": "failed",
            "output": [],
        }

        mock_post.return_value = response

        with self.assertRaises(
            IAProviderError
        ) as context:
            solicitar_json_estructurado_openai(
                **self._kwargs()
            )

        self.assertEqual(
            context.exception.code,
            "structured_response_failed",
        )
