from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.template import Context, Template
from django.test import SimpleTestCase

from .provider_openai import (
    IAProviderError,
    solicitar_json_estructurado_openai,
    solicitar_respuesta_openai,
)
from .services import _crear_instrucciones


CONFIG = {
    "api_key": "test-key",
    "base_url": "https://api.openai.test/v1",
    "model": "gpt-5-test",
    "max_output_tokens": 1200,
    "timeout_seconds": 45,
}


def _response(data, status=200, request_id="req_test"):
    response = Mock()
    response.status_code = status
    response.headers = {"x-request-id": request_id}
    response.json.return_value = data
    return response


class WebSearchProviderTests(SimpleTestCase):
    def _call(self):
        return solicitar_respuesta_openai(
            config=CONFIG,
            transcript="Usuario:\nTiempo en Zamora",
            instructions="Responde con fuentes.",
            safety_identifier="safe-id",
            metadata={"application": "intasa_ia"},
        )

    @patch("intasa_ia.provider_openai.requests.post")
    def test_conversational_payload_enables_web_search(self, post):
        post.return_value = _response({
            "id": "resp_1",
            "model": CONFIG["model"],
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "Actualizado"}],
            }],
        })

        self._call()

        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertTrue(url.endswith("/responses"))
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["reasoning"], {"effort": "low"})

    @patch("intasa_ia.provider_openai.requests.post")
    def test_parser_extracts_text_citations_usage_and_request_id(self, post):
        post.return_value = _response({
            "id": "resp_2",
            "model": CONFIG["model"],
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 7, "total_tokens": 17},
            "output": [
                {"type": "web_search_call", "id": "ws_1"},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "Primero", "annotations": [
                        {"type": "url_citation", "url": "https://example.com/a", "title": "Fuente A"},
                        {"type": "url_citation", "url": "https://example.com/a", "title": "Duplicada"},
                        {"type": "url_citation", "url_citation": {"url": "http://example.org/b", "title": "Fuente B"}},
                    ]},
                    {"type": "output_text", "text": "Segundo", "annotations": [
                        {"type": "url_citation", "url": "javascript:alert(1)", "title": "Mala"},
                        {"type": "url_citation", "url": "data:text/html,bad", "title": "Mala"},
                        {"type": "url_citation", "url": "ftp://example.net/file", "title": "Mala"},
                    ]},
                ]},
            ],
        }, request_id="req_web")

        result = self._call()

        self.assertEqual(result["contenido"], "Primero\n\nSegundo")
        self.assertEqual(result["request_id"], "req_web")
        self.assertEqual(result["tokens_entrada"], 10)
        self.assertEqual(result["tokens_salida"], 7)
        self.assertEqual(result["metadata"]["total_tokens"], 17)
        self.assertIs(result["metadata"]["web_search_available"], True)
        self.assertIs(result["metadata"]["web_search_used"], True)
        self.assertEqual(result["metadata"]["web_citations"], [
            {"title": "Fuente A", "url": "https://example.com/a"},
            {"title": "Fuente B", "url": "http://example.org/b"},
        ])

    @patch("intasa_ia.provider_openai.requests.post")
    def test_citation_without_call_marks_web_search_used(self, post):
        post.return_value = _response({
            "output": [{"type": "message", "content": [{
                "type": "output_text",
                "text": "Dato",
                "annotations": [{"type": "url_citation", "url": "https://example.com", "title": "Fuente"}],
            }]}],
        })
        self.assertIs(self._call()["metadata"]["web_search_used"], True)

    @patch("intasa_ia.provider_openai.requests.post")
    def test_structured_json_has_no_web_tools_and_remains_strict(self, post):
        post.return_value = _response({
            "id": "resp_json",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}],
        })
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}

        solicitar_json_estructurado_openai(
            config=CONFIG,
            input_payload={"value": 1},
            instructions="JSON",
            schema_name="test_schema",
            schema=schema,
            safety_identifier="safe-id",
            metadata={},
        )

        payload = post.call_args.kwargs["json"]
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)
        self.assertEqual(payload["text"]["format"], {
            "type": "json_schema", "name": "test_schema", "schema": schema, "strict": True,
        })

    def test_controlled_provider_errors_do_not_claim_internal_access(self):
        cases = [
            (requests.Timeout(), "timeout"),
            (requests.ConnectionError(), "network_error"),
        ]
        for exception, code in cases:
            with self.subTest(code=code), patch(
                "intasa_ia.provider_openai.requests.post", side_effect=exception
            ):
                with self.assertRaises(IAProviderError) as caught:
                    self._call()
                self.assertEqual(caught.exception.code, code)

        for status, code in [(429, "rate_limit"), (418, "provider_http_error"), (503, "provider_unavailable")]:
            with self.subTest(status=status), patch(
                "intasa_ia.provider_openai.requests.post", return_value=_response({}, status=status)
            ):
                with self.assertRaises(IAProviderError) as caught:
                    self._call()
                self.assertEqual(caught.exception.code, code)


class WebSearchInstructionTests(SimpleTestCase):
    def test_instructions_separate_web_and_internal_data(self):
        instructions = _crear_instrucciones()
        self.assertIn("búsqueda web", instructions)
        self.assertIn("meteorología", instructions)
        self.assertIn("busca antes de responder", instructions)
        self.assertIn("cita las fuentes", instructions)
        self.assertIn("no implica acceso a datos internos", instructions)
        self.assertIn("herramientas internas expresamente habilitadas", instructions)
        self.assertIn("No inventes", instructions)


class WebSearchTemplateTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = (
            Path(__file__).parent / "templates" / "intasa_ia" / "inicio.html"
        ).read_text(encoding="utf-8")

    def test_template_contract_and_safe_links(self):
        self.assertIn("Búsqueda web disponible", self.source)
        self.assertIn("Fuentes consultadas", self.source)
        self.assertIn('target="_blank"', self.source)
        self.assertIn('rel="noopener noreferrer"', self.source)
        self.assertNotIn("|safe", self.source)
        self.assertIn("mensaje.contenido|linebreaksbr", self.source)
        self.assertIn("{% if mensaje.metadata.web_citations %}", self.source)

    def test_citations_fragment_is_absent_without_citations(self):
        fragment = Template("""
            {% if citations %}<div>Fuentes consultadas</div>{% endif %}
        """)
        self.assertNotIn("Fuentes consultadas", fragment.render(Context({"citations": []})))

