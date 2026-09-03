from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlencode

from django import template
from django.urls import reverse
from django.utils.http import (
    url_has_allowed_host_and_scheme,
)


register = template.Library()


def _normalize_storage_key(value: str) -> str:
    parts = [
        part
        for part in str(value or "")
        .replace("\\", "/")
        .split("/")
        if part not in ("", ".", "..")
    ]

    return "/".join(parts)


def _parent_path(storage_key: str) -> str:
    normalized = _normalize_storage_key(
        storage_key
    )

    if not normalized:
        return ""

    parent = str(
        PurePosixPath(normalized).parent
    )

    return "" if parent == "." else parent


def _explorer_url(path: str = "") -> str:
    url = reverse(
        "archivos:explorador_raiz"
    )

    normalized = _normalize_storage_key(
        path
    )

    if normalized:
        url += "?" + urlencode(
            {
                "path": normalized,
            }
        )

    return url


@register.simple_tag(
    takes_context=True
)
def document_return_url(
    context,
    archivo,
) -> str:
    request = context.get("request")

    fallback = _explorer_url(
        _parent_path(
            getattr(
                archivo,
                "storage_key",
                "",
            )
        )
    )

    if request is None:
        return fallback

    candidate = str(
        request.GET.get("next")
        or ""
    ).strip()

    if (
        candidate
        and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={
                request.get_host(),
            },
            require_https=request.is_secure(),
        )
    ):
        return candidate

    return fallback


@register.simple_tag
def document_detail_url(
    archivo,
    return_url: str,
) -> str:
    url = reverse(
        "archivos:archivo_detalle",
        args=[archivo.pk],
    )

    return url + "?" + urlencode(
        {
            "next": return_url,
        }
    )


@register.simple_tag
def document_editor_url(
    archivo,
    return_url: str,
) -> str:
    url = reverse(
        "archivos:archivo_editar_online",
        args=[archivo.pk],
    )

    return url + "?" + urlencode(
        {
            "next": return_url,
        }
    )


@register.simple_tag
def document_breadcrumbs(
    archivo,
) -> list[dict]:
    storage_key = _normalize_storage_key(
        getattr(
            archivo,
            "storage_key",
            "",
        )
    )

    parent = _parent_path(
        storage_key
    )

    crumbs = [
        {
            "name": "Archivos",
            "url": _explorer_url(""),
        }
    ]

    accumulated = []

    for part in parent.split("/"):
        if not part:
            continue

        accumulated.append(part)

        crumbs.append(
            {
                "name": part,
                "url": _explorer_url(
                    "/".join(
                        accumulated
                    )
                ),
            }
        )

    return crumbs


@register.simple_tag
def cloud_parent(
    storage_key: str,
) -> str:
    return _parent_path(
        storage_key
    )


@register.filter
def human_size(value) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0

    units = (
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
    )

    for unit in units:
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.2f} {unit}"

        size /= 1024

    return "0 B"
