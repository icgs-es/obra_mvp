"""
INTASA IA · Recuperación prioritaria de Ayuda Interna.

La biblioteca Markdown se consulta antes de generar una respuesta.
Solo se utilizan artículos visibles para el usuario.
"""

from __future__ import annotations

from contextvars import ContextVar
import inspect

from ayuda.services import (
    get_article,
    search_articles,
)

from . import services as _core_services


_HELP_CONTEXT: ContextVar[str] = ContextVar(
    "intasa_ia_help_context",
    default="",
)

_ORIGINAL_TRANSCRIPTION = (
    _core_services._crear_transcripcion
)

_MINIMUM_HELP_SCORE = 45
_MAX_ARTICLES = 4
_MAX_ARTICLE_CHARACTERS = 3600
_MAX_TOTAL_CONTEXT_CHARACTERS = 10500


def _crear_transcripcion_con_ayuda(
    conversacion,
):
    """
    Añade documentación interna autorizada a la transcripción.

    ContextVar mantiene el aislamiento entre peticiones
    concurrentes y evita compartir contexto entre usuarios.
    """

    transcript = _ORIGINAL_TRANSCRIPTION(
        conversacion
    )

    help_context = _HELP_CONTEXT.get()

    if not help_context:
        return transcript

    return (
        transcript.rstrip()
        + "\n\n"
        + help_context
    )


# El servicio original continuará utilizando su función global
# _crear_transcripcion, pero esta incorporará el contexto autorizado.
_core_services._crear_transcripcion = (
    _crear_transcripcion_con_ayuda
)


def _bind_arguments(
    args,
    kwargs,
):
    try:
        signature = inspect.signature(
            _core_services.generar_respuesta_segura
        )

        return signature.bind_partial(
            *args,
            **kwargs,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _find_argument(
    bound,
    kwargs,
    names,
):
    for name in names:
        if name in kwargs:
            return kwargs[name]

    if bound is not None:
        for name in names:
            if name in bound.arguments:
                return bound.arguments[name]

    return None


def _latest_user_question(
    conversation,
):
    if conversation is None:
        return ""

    manager = getattr(
        conversation,
        "mensajes",
        None,
    )

    if manager is None:
        return ""

    try:
        message = (
            manager
            .filter(rol="USUARIO")
            .order_by(
                "-created_at",
                "-id",
            )
            .first()
        )

    except Exception:
        return ""

    if message is None:
        return ""

    return str(
        getattr(
            message,
            "contenido",
            "",
        )
        or ""
    ).strip()


def _extract_call_context(
    args,
    kwargs,
):
    bound = _bind_arguments(
        args,
        kwargs,
    )

    question = _find_argument(
        bound,
        kwargs,
        (
            "pregunta",
            "consulta",
            "question",
            "texto",
            "mensaje",
            "contenido",
            "prompt",
            "user_message",
            "mensaje_usuario",
        ),
    )

    user = _find_argument(
        bound,
        kwargs,
        (
            "user",
            "usuario",
        ),
    )

    conversation = _find_argument(
        bound,
        kwargs,
        (
            "conversacion",
            "conversation",
        ),
    )

    question = str(
        question or ""
    ).strip()

    if (
        not question
        and conversation is not None
    ):
        question = _latest_user_question(
            conversation
        )

    if (
        user is None
        and conversation is not None
    ):
        user = getattr(
            conversation,
            "user",
            None,
        )

    return (
        question,
        user,
        conversation,
    )


def _select_relevant_results(
    question,
    user,
):
    if (
        not question
        or user is None
    ):
        return []

    results = search_articles(
        question,
        user,
        context_path="",
        limit=8,
    )

    selected = [
        result
        for result in results
        if int(
            result.get("score") or 0
        ) >= _MINIMUM_HELP_SCORE
    ]

    return selected[:_MAX_ARTICLES]


def _build_help_payload(
    question,
    user,
):
    results = _select_relevant_results(
        question,
        user,
    )

    if not results:
        return {
            "context": "",
            "sources": [],
            "articles": [],
        }

    context_parts = [
        (
            "[DOCUMENTACIÓN INTERNA AUTORIZADA "
            "DE PORTAL INTASA]"
        ),
        (
            "Utiliza esta documentación como fuente "
            "prioritaria para responder la pregunta."
        ),
        (
            "No inventes procedimientos, estados, "
            "permisos ni efectos que no estén descritos."
        ),
        (
            "La documentación explica funcionamiento "
            "y procedimientos, pero no demuestra datos "
            "reales de una factura, usuario u operación."
        ),
        (
            "Cuando la pregunta requiera datos concretos "
            "que no aparecen aquí, indícalo claramente."
        ),
        (
            "Al final de la respuesta menciona los títulos "
            "de las fuentes internas realmente utilizadas."
        ),
    ]

    sources = []
    articles = []
    total_characters = 0

    for result in results:
        article = get_article(
            result["id"],
            user,
        )

        if article is None:
            continue

        body = (
            article.body
            or article.summary
            or ""
        ).strip()

        body = body[
            :_MAX_ARTICLE_CHARACTERS
        ]

        remaining = (
            _MAX_TOTAL_CONTEXT_CHARACTERS
            - total_characters
        )

        if remaining <= 0:
            break

        body = body[:remaining]

        article_block = (
            "\n\n---\n"
            f"FUENTE: {article.title}\n"
            f"ID: {article.article_id}\n"
            f"MÓDULO: {article.module} · "
            f"{article.submodule}\n\n"
            f"{body}"
        )

        context_parts.append(
            article_block
        )

        total_characters += len(body)

        sources.append(
            {
                "id": article.article_id,
                "titulo": article.title,
                "modulo": article.module,
                "submodulo": article.submodule,
                "score": int(
                    result.get("score") or 0
                ),
            }
        )

        articles.append(article)

    if not sources:
        return {
            "context": "",
            "sources": [],
            "articles": [],
        }

    return {
        "context": "\n".join(
            context_parts
        ),
        "sources": sources,
        "articles": articles,
    }


def _source_titles(
    sources,
):
    return [
        source["titulo"]
        for source in sources
        if source.get("titulo")
    ]


def _source_footer(
    sources,
):
    titles = _source_titles(
        sources
    )

    if not titles:
        return ""

    return (
        "\n\nFuentes internas consultadas: "
        + "; ".join(titles)
        + "."
    )


def _merge_metadata(
    result,
    sources,
):
    metadata = result.get(
        "metadata"
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    metadata = dict(metadata)

    metadata.update(
        {
            "ayuda_interna_consultada": bool(
                sources
            ),
            "ayuda_interna_fuente": (
                "docs/ayuda"
            ),
            "ayuda_interna_articulos": (
                sources
            ),
        }
    )

    result["metadata"] = metadata


def _build_local_help_answer(
    result,
    payload,
):
    articles = payload["articles"]
    sources = payload["sources"]

    if not articles:
        return result

    first = articles[0]

    content_parts = [
        first.title,
        "",
        (
            first.body
            or first.summary
            or ""
        ).strip()[:2600],
    ]

    if len(articles) > 1:
        content_parts.extend(
            [
                "",
                "También pueden resultar útiles:",
            ]
        )

        for article in articles[1:]:
            content_parts.append(
                f"- {article.title}"
            )

    content = "\n".join(
        content_parts
    ).strip()

    content += _source_footer(
        sources
    )

    result["contenido"] = content
    result["proveedor"] = "local-help"
    result["modelo"] = "ayuda-interna-v1"

    result.setdefault(
        "request_id",
        "",
    )

    result.setdefault(
        "tokens_entrada",
        None,
    )

    result.setdefault(
        "tokens_salida",
        None,
    )

    _merge_metadata(
        result,
        sources,
    )

    return result


def _finalize_generated_result(
    result,
    payload,
):
    if not isinstance(
        result,
        dict,
    ):
        return result

    sources = payload["sources"]

    if not sources:
        return result

    if (
        result.get("proveedor")
        == "local-safe"
    ):
        return _build_local_help_answer(
            dict(result),
            payload,
        )

    result = dict(result)

    content = str(
        result.get("contenido") or ""
    ).strip()

    footer = _source_footer(
        sources
    )

    if (
        footer
        and "Fuentes internas consultadas:"
        not in content
    ):
        result["contenido"] = (
            content + footer
        ).strip()

    _merge_metadata(
        result,
        sources,
    )

    return result


def generar_respuesta_segura(
    *args,
    **kwargs,
):
    """
    Wrapper compatible con la firma del servicio original.
    """

    (
        question,
        user,
        _conversation,
    ) = _extract_call_context(
        args,
        kwargs,
    )

    payload = _build_help_payload(
        question,
        user,
    )

    token = _HELP_CONTEXT.set(
        payload["context"]
    )

    try:
        result = (
            _core_services
            .generar_respuesta_segura(
                *args,
                **kwargs,
            )
        )

    finally:
        _HELP_CONTEXT.reset(
            token
        )

    return _finalize_generated_result(
        result,
        payload,
    )
