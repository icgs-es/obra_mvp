from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path
import re
import unicodedata

from django.conf import settings


HELP_ROOT = Path(settings.BASE_DIR) / "docs" / "ayuda"


@dataclass(frozen=True)
class HelpArticle:
    article_id: str
    title: str
    module: str
    submodule: str
    summary: str
    keywords: tuple[str, ...]
    permissions: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    order: int
    updated: str
    body: str
    source_path: str


class HelpDocumentError(ValueError):
    pass


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip()
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value or "",
    )

    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"\s+",
        " ",
        without_accents.lower(),
    ).strip()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(
            r"[a-z0-9]{2,}",
            _normalize(value),
        )
        if token
    )


def _parse_document(path: Path) -> HelpArticle:
    raw = path.read_text(encoding="utf-8")

    if not raw.startswith("---\n"):
        raise HelpDocumentError(
            f"{path}: falta cabecera inicial ---"
        )

    separator = "\n---\n"

    if separator not in raw[4:]:
        raise HelpDocumentError(
            f"{path}: falta cierre de cabecera ---"
        )

    header_text, body = raw[4:].split(
        separator,
        1,
    )

    metadata: dict[str, str] = {}

    for line_number, line in enumerate(
        header_text.splitlines(),
        start=2,
    ):
        stripped = line.strip()

        if not stripped:
            continue

        if ":" not in stripped:
            raise HelpDocumentError(
                f"{path}:{line_number}: "
                "metadato sin ':'"
            )

        key, value = stripped.split(":", 1)

        metadata[key.strip()] = value.strip()

    required = (
        "id",
        "titulo",
        "modulo",
        "submodulo",
    )

    missing = [
        key
        for key in required
        if not metadata.get(key)
    ]

    if missing:
        raise HelpDocumentError(
            f"{path}: faltan metadatos "
            + ", ".join(missing)
        )

    try:
        order = int(
            metadata.get("orden", "100")
        )
    except ValueError as exc:
        raise HelpDocumentError(
            f"{path}: orden no válido"
        ) from exc

    article_id = metadata["id"]

    if not re.fullmatch(
        r"[a-z0-9_.-]+",
        article_id,
    ):
        raise HelpDocumentError(
            f"{path}: id documental no válido "
            f"{article_id!r}"
        )

    permissions = _split_csv(
        metadata.get("permisos", "")
    )

    for permission in permissions:
        if "." not in permission:
            raise HelpDocumentError(
                f"{path}: permiso no válido "
                f"{permission!r}"
            )

    return HelpArticle(
        article_id=article_id,
        title=metadata["titulo"],
        module=metadata["modulo"],
        submodule=metadata["submodulo"],
        summary=metadata.get(
            "resumen",
            "",
        ),
        keywords=_split_csv(
            metadata.get(
                "palabras_clave",
                "",
            )
        ),
        permissions=permissions,
        path_prefixes=_split_csv(
            metadata.get(
                "rutas",
                "",
            )
        ),
        order=order,
        updated=metadata.get(
            "actualizado",
            "",
        ),
        body=body.strip(),
        source_path=str(path),
    )


def _library_signature() -> tuple:
    if not HELP_ROOT.exists():
        return tuple()

    return tuple(
        (
            str(path),
            path.stat().st_mtime_ns,
            path.stat().st_size,
        )
        for path in sorted(
            HELP_ROOT.rglob("*.md")
        )
    )


@lru_cache(maxsize=8)
def _load_cached(
    signature: tuple,
) -> tuple[HelpArticle, ...]:
    del signature

    articles = [
        _parse_document(path)
        for path in sorted(
            HELP_ROOT.rglob("*.md")
        )
    ]

    identifiers = [
        article.article_id
        for article in articles
    ]

    duplicates = sorted(
        {
            identifier
            for identifier in identifiers
            if identifiers.count(identifier) > 1
        }
    )

    if duplicates:
        raise HelpDocumentError(
            "IDs documentales duplicados: "
            + ", ".join(duplicates)
        )

    return tuple(
        sorted(
            articles,
            key=lambda article: (
                article.order,
                _normalize(article.module),
                _normalize(article.submodule),
                _normalize(article.title),
            ),
        )
    )


def get_all_articles() -> tuple[HelpArticle, ...]:
    return _load_cached(
        _library_signature()
    )


def validate_library() -> tuple[HelpArticle, ...]:
    return get_all_articles()


def user_can_view(
    user,
    article: HelpArticle,
) -> bool:
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return False

    # AYUDA_USER_WITHOUT_PK_FAIL_CLOSED_V1
    # Un usuario no persistido no puede tener permisos efectivos.
    if getattr(user, "pk", None) is None:
        return False

    if getattr(
        user,
        "is_superuser",
        False,
    ):
        return True

    return all(
        user.has_perm(permission)
        for permission in article.permissions
    )


def visible_articles(user) -> tuple[HelpArticle, ...]:
    return tuple(
        article
        for article in get_all_articles()
        if user_can_view(
            user,
            article,
        )
    )


def _plain_text(body: str) -> str:
    text = re.sub(
        r"[#>*_`]",
        " ",
        body,
    )

    text = re.sub(
        r"^\s*[-+]\s+",
        "",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"^\s*\d+\.\s+",
        "",
        text,
        flags=re.MULTILINE,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _snippet(
    article: HelpArticle,
    query: str,
    length: int = 230,
) -> str:
    plain = _plain_text(
        article.body
    )

    if not plain:
        return article.summary

    normalized_plain = _normalize(
        plain
    )

    query_tokens = _tokens(query)

    position = -1

    for token in query_tokens:
        position = normalized_plain.find(
            token
        )

        if position >= 0:
            break

    if position < 0:
        start = 0
    else:
        start = max(
            0,
            position - 70,
        )

    fragment = plain[
        start:start + length
    ].strip()

    if start > 0:
        fragment = "…" + fragment

    if (
        start + length
        < len(plain)
    ):
        fragment += "…"

    return fragment


def search_articles(
    query: str,
    user,
    *,
    context_path: str = "",
    limit: int = 8,
) -> list[dict]:
    query = (query or "").strip()[:160]
    query_normalized = _normalize(query)
    query_tokens = _tokens(query)
    context_path = (
        context_path or ""
    ).strip()[:500]

    ranked: list[
        tuple[int, HelpArticle]
    ] = []

    for article in visible_articles(user):
        title = _normalize(
            article.title
        )
        summary = _normalize(
            article.summary
        )
        keywords = _normalize(
            " ".join(
                article.keywords
            )
        )
        body = _normalize(
            article.body
        )
        module = _normalize(
            article.module
            + " "
            + article.submodule
        )

        score = 0

        if query_normalized:
            if query_normalized == title:
                score += 160
            elif query_normalized in title:
                score += 100

            if query_normalized in keywords:
                score += 70

            if query_normalized in summary:
                score += 35

            if query_normalized in body:
                score += 20

            for token in query_tokens:
                if token in title:
                    score += 24

                if token in keywords:
                    score += 16

                if token in module:
                    score += 10

                if token in summary:
                    score += 8

                if token in body:
                    score += 3

        else:
            score = 1

        if context_path:
            for prefix in article.path_prefixes:
                if context_path.startswith(
                    prefix
                ):
                    score += 55
                    break

        if score > 0:
            ranked.append(
                (
                    score,
                    article,
                )
            )

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].order,
            _normalize(
                item[1].title
            ),
        )
    )

    results = []

    for score, article in ranked[:limit]:
        results.append(
            {
                "id": article.article_id,
                "titulo": article.title,
                "modulo": article.module,
                "submodulo": article.submodule,
                "resumen": (
                    article.summary
                    or _snippet(
                        article,
                        query,
                    )
                ),
                "fragmento": _snippet(
                    article,
                    query,
                ),
                "actualizado": article.updated,
                "score": score,
            }
        )

    return results


def get_article(
    article_id: str,
    user,
) -> HelpArticle | None:
    for article in visible_articles(user):
        if article.article_id == article_id:
            return article

    return None


def _inline_markup(value: str) -> str:
    safe = escape(
        value,
        quote=True,
    )

    safe = re.sub(
        r"`([^`]+)`",
        r"<code>\1</code>",
        safe,
    )

    safe = re.sub(
        r"\*\*([^*]+)\*\*",
        r"<strong>\1</strong>",
        safe,
    )

    return safe


def render_markdown_safe(
    body: str,
) -> str:
    output: list[str] = []
    current_list = None

    def close_list():
        nonlocal current_list

        if current_list:
            output.append(
                f"</{current_list}>"
            )
            current_list = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            close_list()
            continue

        heading = re.match(
            r"^(#{1,3})\s+(.+)$",
            line,
        )

        if heading:
            close_list()

            level = len(
                heading.group(1)
            )

            output.append(
                f"<h{level + 1}>"
                + _inline_markup(
                    heading.group(2)
                )
                + f"</h{level + 1}>"
            )
            continue

        unordered = re.match(
            r"^\s*[-+]\s+(.+)$",
            line,
        )

        if unordered:
            if current_list != "ul":
                close_list()
                output.append("<ul>")
                current_list = "ul"

            output.append(
                "<li>"
                + _inline_markup(
                    unordered.group(1)
                )
                + "</li>"
            )
            continue

        ordered = re.match(
            r"^\s*\d+\.\s+(.+)$",
            line,
        )

        if ordered:
            if current_list != "ol":
                close_list()
                output.append("<ol>")
                current_list = "ol"

            output.append(
                "<li>"
                + _inline_markup(
                    ordered.group(1)
                )
                + "</li>"
            )
            continue

        quote = re.match(
            r"^\s*>\s*(.+)$",
            line,
        )

        if quote:
            close_list()

            output.append(
                "<blockquote>"
                + _inline_markup(
                    quote.group(1)
                )
                + "</blockquote>"
            )
            continue

        close_list()

        output.append(
            "<p>"
            + _inline_markup(
                line.strip()
            )
            + "</p>"
        )

    close_list()

    return "\n".join(output)
