import hashlib
import json
import re
import logging
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

import requests


logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(
    os.environ.get(
        "INTASA_IA_CONFIG_PATH",
        "/app/infra/secrets/openai_intasa.json",
    )
)


class IAProviderError(RuntimeError):
    def __init__(
        self,
        code,
        *,
        request_id="",
        http_status=None,
    ):
        super().__init__(code)
        self.code = str(code)
        self.request_id = str(request_id or "")
        self.http_status = http_status


def cargar_config_openai(path=None):
    path = Path(path or DEFAULT_CONFIG_PATH)

    if not path.is_file():
        raise IAProviderError("config_missing")

    mode = stat.S_IMODE(path.stat().st_mode)

    if mode & 0o077:
        raise IAProviderError("config_permissions_insecure")

    try:
        config = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise IAProviderError(
            "config_invalid"
        ) from exc

    enabled = bool(config.get("enabled", False))
    api_key = str(config.get("api_key", "")).strip()
    model = str(config.get("model", "")).strip()

    base_url = str(
        config.get(
            "base_url",
            "https://api.openai.com/v1",
        )
    ).rstrip("/")

    try:
        timeout_seconds = int(
            config.get("timeout_seconds", 45)
        )
    except (TypeError, ValueError) as exc:
        raise IAProviderError(
            "timeout_invalid"
        ) from exc

    try:
        max_output_tokens = int(
            config.get("max_output_tokens", 1200)
        )
    except (TypeError, ValueError) as exc:
        raise IAProviderError(
            "max_output_tokens_invalid"
        ) from exc

    if not api_key:
        raise IAProviderError("api_key_missing")

    if enabled and not model:
        raise IAProviderError("model_missing")

    if not base_url.startswith("https://"):
        raise IAProviderError("base_url_invalid")

    if not 5 <= timeout_seconds <= 120:
        raise IAProviderError("timeout_invalid")

    if not 100 <= max_output_tokens <= 4000:
        raise IAProviderError(
            "max_output_tokens_invalid"
        )

    if bool(config.get("store", False)):
        raise IAProviderError(
            "store_must_be_false"
        )

    return {
        "enabled": enabled,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "max_output_tokens": max_output_tokens,
        "store": False,
    }


def obtener_estado_proveedor():
    try:
        config = cargar_config_openai()
    except IAProviderError as exc:
        return {
            "enabled": False,
            "configured": False,
            "model": "",
            "error": exc.code,
        }

    return {
        "enabled": bool(config["enabled"]),
        "configured": bool(config["api_key"]),
        "model": config["model"],
        "error": "",
    }


def crear_safety_identifier(user_id):
    raw = f"intasa-platform:{user_id}".encode(
        "utf-8"
    )

    return hashlib.sha256(raw).hexdigest()


def _extraer_texto_respuesta(data):
    pieces = []
    refusals = []

    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue

        for content in item.get("content") or []:
            content_type = content.get("type")

            if content_type == "output_text":
                text = str(
                    content.get("text", "")
                ).strip()

                if text:
                    pieces.append(text)

            elif content_type == "refusal":
                refusal = str(
                    content.get("refusal", "")
                ).strip()

                if refusal:
                    refusals.append(refusal)

    if pieces:
        return "\n\n".join(pieces)

    if refusals:
        return "\n\n".join(refusals)

    return ""


def _normalizar_cita_web(annotation):
    if not isinstance(annotation, dict):
        return None

    citation = annotation
    if annotation.get("type") == "url_citation":
        nested = annotation.get("url_citation")
        if isinstance(nested, dict):
            citation = nested
    else:
        return None

    url = str(citation.get("url") or "").strip()
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    url = url[:2048]
    title = str(citation.get("title") or "").strip()[:300]

    return {
        "title": title or url,
        "url": url,
    }


def _extraer_metadatos_web(data):
    web_search_used = False
    citations = []
    seen_urls = set()

    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue

        if item.get("type") == "web_search_call":
            web_search_used = True

        if item.get("type") != "message":
            continue

        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue

            for annotation in content.get("annotations") or []:
                citation = _normalizar_cita_web(annotation)
                if citation is None:
                    continue

                url = citation["url"]
                if url in seen_urls:
                    continue

                seen_urls.add(url)
                citations.append(citation)

    return web_search_used or bool(citations), citations


def _codigo_error_http(status):
    if status == 400:
        return "invalid_request"

    if status == 401:
        return "authentication_error"

    if status == 403:
        return "permission_error"

    if status == 429:
        return "rate_limit"

    if status >= 500:
        return "provider_unavailable"

    return "provider_http_error"


def solicitar_respuesta_openai(
    *,
    config,
    transcript,
    instructions,
    safety_identifier,
    metadata,
    web_search_enabled=True,
):
    payload = {
        "model": config["model"],
        "instructions": instructions,
        "input": transcript,
        "max_output_tokens": (
            config["max_output_tokens"]
        ),
        "store": False,
        "safety_identifier": safety_identifier,
        "metadata": {
            str(key)[:64]: str(value)[:512]
            for key, value in metadata.items()
        },
    }

    if web_search_enabled:
        payload["tools"] = [{"type": "web_search"}]
        payload["tool_choice"] = "auto"

    if config["model"].startswith("gpt-5"):
        payload["reasoning"] = {
            "effort": "low",
        }

    try:
        response = requests.post(
            f'{config["base_url"]}/responses',
            headers={
                "Authorization": (
                    f'Bearer {config["api_key"]}'
                ),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(
                10,
                config["timeout_seconds"],
            ),
        )
    except requests.Timeout as exc:
        raise IAProviderError(
            "timeout"
        ) from exc
    except requests.RequestException as exc:
        raise IAProviderError(
            "network_error"
        ) from exc

    request_id = response.headers.get(
        "x-request-id",
        "",
    )

    if not 200 <= response.status_code < 300:
        logger.warning(
            "INTASA IA OpenAI HTTP %s request_id=%s",
            response.status_code,
            request_id,
        )

        raise IAProviderError(
            _codigo_error_http(
                response.status_code
            ),
            request_id=request_id,
            http_status=response.status_code,
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise IAProviderError(
            "invalid_json",
            request_id=request_id,
            http_status=response.status_code,
        ) from exc

    contenido = _extraer_texto_respuesta(data)
    web_search_used, web_citations = (
        _extraer_metadatos_web(data)
    )

    if not contenido:
        raise IAProviderError(
            "empty_response",
            request_id=request_id,
            http_status=response.status_code,
        )

    usage = data.get("usage") or {}

    return {
        "contenido": contenido,
        "proveedor": "openai",
        "modelo": str(
            data.get("model")
            or config["model"]
        ),
        "request_id": (
            request_id
            or str(data.get("id", ""))
        ),
        "tokens_entrada": (
            usage.get("input_tokens")
        ),
        "tokens_salida": (
            usage.get("output_tokens")
        ),
        "metadata": {
            "external_call": True,
            "read_only": True,
            "store": False,
            "response_id": str(
                data.get("id", "")
            ),
            "status": str(
                data.get("status", "")
            ),
            "total_tokens": (
                usage.get("total_tokens")
            ),
            "web_search_available": bool(web_search_enabled),
            "web_search_used": web_search_used,
            "web_citations": web_citations,
        },
    }


# INTASA_IA_STRUCTURED_JSON_V1


def _validar_nombre_schema_estructurado(
    value,
):
    value = str(
        value or ""
    ).strip()

    if not value:
        raise IAProviderError(
            "structured_schema_name_invalid"
        )

    if len(value) > 64:
        raise IAProviderError(
            "structured_schema_name_invalid"
        )

    if not all(
        char.isalnum()
        or char in "_-"
        for char in value
    ):
        raise IAProviderError(
            "structured_schema_name_invalid"
        )

    return value


def _validar_schema_estructurado(
    schema,
):
    if not isinstance(
        schema,
        dict,
    ):
        raise IAProviderError(
            "structured_schema_invalid"
        )

    if schema.get("type") != "object":
        raise IAProviderError(
            "structured_schema_invalid"
        )

    return schema


def solicitar_json_estructurado_openai(
    *,
    config,
    input_payload,
    instructions,
    schema_name,
    schema,
    safety_identifier,
    metadata,
):
    """
    Ejecuta Responses API con Structured Outputs.

    No conoce comparativas ni reglas de negocio.
    Devuelve JSON parseado y metadatos del proveedor.
    """

    schema_name = (
        _validar_nombre_schema_estructurado(
            schema_name
        )
    )

    schema = (
        _validar_schema_estructurado(
            schema
        )
    )

    try:
        input_text = json.dumps(
            input_payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise IAProviderError(
            "structured_input_invalid"
        ) from exc

    payload = {
        "model": config["model"],
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": (
            config[
                "max_output_tokens"
            ]
        ),
        "store": False,
        "safety_identifier": (
            safety_identifier
        ),
        "metadata": {
            str(key)[:64]: str(value)[:512]
            for key, value
            in metadata.items()
        },
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }

    if config[
        "model"
    ].startswith("gpt-5"):
        payload["reasoning"] = {
            "effort": "low",
        }

    try:
        response = requests.post(
            (
                f'{config["base_url"]}'
                "/responses"
            ),
            headers={
                "Authorization": (
                    f'Bearer '
                    f'{config["api_key"]}'
                ),
                "Content-Type": (
                    "application/json"
                ),
            },
            json=payload,
            timeout=(
                10,
                config[
                    "timeout_seconds"
                ],
            ),
        )

    except requests.Timeout as exc:
        raise IAProviderError(
            "timeout"
        ) from exc

    except requests.RequestException as exc:
        raise IAProviderError(
            "network_error"
        ) from exc

    request_id = (
        response.headers.get(
            "x-request-id",
            "",
        )
    )

    if not (
        200
        <= response.status_code
        < 300
    ):
        logger.warning(
            (
                "INTASA IA structured "
                "OpenAI HTTP %s "
                "request_id=%s"
            ),
            response.status_code,
            request_id,
        )

        raise IAProviderError(
            _codigo_error_http(
                response.status_code
            ),
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    try:
        data = response.json()

    except ValueError as exc:
        raise IAProviderError(
            "invalid_json",
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        ) from exc

    # Structured Outputs necesita distinguir el
    # estado terminal antes de interpretar output_text.
    #
    # Una respuesta HTTP 2xx puede finalizar como
    # incomplete, failed, cancelled, etc. También puede
    # contener un bloque refusal en lugar de JSON.
    status = str(
        data.get(
            "status",
            "",
        )
        or ""
    ).strip().lower()

    if status == "incomplete":
        incomplete_details = (
            data.get(
                "incomplete_details"
            )
            or {}
        )

        reason = str(
            incomplete_details.get(
                "reason",
                "",
            )
            or "unknown"
        ).strip().lower()

        reason = re.sub(
            r"[^a-z0-9]+",
            "_",
            reason,
        ).strip("_")

        if not reason:
            reason = "unknown"

        raise IAProviderError(
            (
                "structured_incomplete_"
                + reason
            ),
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    if (
        status
        and status
        != "completed"
    ):
        safe_status = re.sub(
            r"[^a-z0-9]+",
            "_",
            status,
        ).strip("_")

        raise IAProviderError(
            (
                "structured_response_"
                + (
                    safe_status
                    or "unknown"
                )
            ),
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    refusals = []

    for item in (
        data.get("output")
        or []
    ):
        if (
            item.get("type")
            != "message"
        ):
            continue

        for content in (
            item.get("content")
            or []
        ):
            if (
                content.get("type")
                != "refusal"
            ):
                continue

            refusal = str(
                content.get(
                    "refusal",
                    "",
                )
            ).strip()

            if refusal:
                refusals.append(
                    refusal
                )

    if refusals:
        raise IAProviderError(
            "structured_refusal",
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    contenido = (
        _extraer_texto_respuesta(
            data
        )
    )

    if not contenido:
        raise IAProviderError(
            "empty_response",
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    try:
        structured_data = (
            json.loads(
                contenido
            )
        )

    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise IAProviderError(
            "structured_invalid_json",
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        ) from exc

    if not isinstance(
        structured_data,
        dict,
    ):
        raise IAProviderError(
            "structured_root_not_object",
            request_id=request_id,
            http_status=(
                response.status_code
            ),
        )

    usage = (
        data.get("usage")
        or {}
    )

    return {
        "datos": structured_data,
        "proveedor": "openai",
        "modelo": str(
            data.get("model")
            or config["model"]
        ),
        "request_id": (
            request_id
            or str(
                data.get(
                    "id",
                    "",
                )
            )
        ),
        "tokens_entrada": (
            usage.get(
                "input_tokens"
            )
        ),
        "tokens_salida": (
            usage.get(
                "output_tokens"
            )
        ),
        "metadata": {
            "external_call": True,
            "read_only": True,
            "store": False,
            "structured": True,
            "schema_name": (
                schema_name
            ),
            "strict": True,
            "response_id": str(
                data.get(
                    "id",
                    "",
                )
            ),
            "status": str(
                data.get(
                    "status",
                    "",
                )
            ),
            "total_tokens": (
                usage.get(
                    "total_tokens"
                )
            ),
        },
    }
