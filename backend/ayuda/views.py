from collections import OrderedDict

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from .services import (
    get_article,
    render_markdown_safe,
    search_articles,
    visible_articles,
)


def _module_tree(user):
    modules = OrderedDict()

    for article in visible_articles(user):
        module = modules.setdefault(
            article.module,
            OrderedDict(),
        )

        module.setdefault(
            article.submodule,
            [],
        ).append(article)

    return [
        {
            "nombre": module_name,
            "submodulos": [
                {
                    "nombre": submodule_name,
                    "articulos": articles,
                }
                for (
                    submodule_name,
                    articles,
                ) in submodules.items()
            ],
        }
        for (
            module_name,
            submodules,
        ) in modules.items()
    ]


@login_required
@require_GET
def centro(request):
    query = (
        request.GET.get("q")
        or ""
    ).strip()

    context_path = (
        request.GET.get("from")
        or ""
    ).strip()

    results = []

    if query:
        results = search_articles(
            query,
            request.user,
            context_path=context_path,
            limit=20,
        )

        for result in results:
            result["url"] = reverse(
                "ayuda:articulo",
                kwargs={
                    "article_id": (
                        result["id"]
                    )
                },
            )

    return render(
        request,
        "ayuda/centro.html",
        {
            "query": query,
            "context_path": context_path,
            "modules": _module_tree(
                request.user
            ),
            "results": results,
        },
    )


@login_required
@require_GET
def buscar_api(request):
    query = (
        request.GET.get("q")
        or ""
    ).strip()

    context_path = (
        request.GET.get("context")
        or ""
    ).strip()

    results = search_articles(
        query,
        request.user,
        context_path=context_path,
        limit=8,
    )

    for result in results:
        result["url"] = reverse(
            "ayuda:articulo",
            kwargs={
                "article_id": result["id"],
            },
        )

    return JsonResponse(
        {
            "ok": True,
            "query": query,
            "context": context_path,
            "total": len(results),
            "resultados": results,
        }
    )


# AYUDA_ARTICLE_PANEL_VIEW_V1
@login_required
@require_GET
def articulo_api(request, article_id):
    article = get_article(
        article_id,
        request.user,
    )

    if article is None:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Artículo no encontrado "
                    "o no autorizado."
                ),
            },
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "articulo": {
                "id": article.article_id,
                "titulo": article.title,
                "modulo": article.module,
                "submodulo": article.submodule,
                "resumen": article.summary,
                "actualizado": article.updated,
                "html": render_markdown_safe(
                    article.body
                ),
                "url_completa": reverse(
                    "ayuda:articulo",
                    kwargs={
                        "article_id": (
                            article.article_id
                        )
                    },
                ),
            },
        }
    )


@login_required
@require_GET
def articulo(request, article_id):
    article = get_article(
        article_id,
        request.user,
    )

    if article is None:
        from django.http import Http404

        raise Http404(
            "Artículo de ayuda no encontrado."
        )

    related = [
        candidate
        for candidate in visible_articles(
            request.user
        )
        if (
            candidate.article_id
            != article.article_id
            and candidate.module
            == article.module
            and candidate.submodule
            == article.submodule
        )
    ][:4]

    return render(
        request,
        "ayuda/articulo.html",
        {
            "article": article,
            "body_html": mark_safe(
                render_markdown_safe(
                    article.body
                )
            ),
            "related": related,
        },
    )
