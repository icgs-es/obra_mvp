from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_required
from django.http import (
    Http404,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET

from .models import Archivo
from .storage_providers import get_storage_provider
from .storage_providers.base import StorageProviderError
from .views import _can_access_file


PASSTHROUGH_HEADERS = (
    "Content-Length",
    "Content-Range",
    "ETag",
    "Last-Modified",
)


@login_required
@require_GET
def media_stream(request, file_id: int):
    archivo = get_object_or_404(
        Archivo,
        pk=file_id,
        storage_provider="nextcloud",
    )

    if not _can_access_file(
        request.user,
        archivo,
    ):
        raise Http404()

    provider = get_storage_provider(
        "nextcloud"
    )

    remote_path = provider._remote_path(
        archivo
    )

    request_headers = {}

    range_header = str(
        request.headers.get("Range")
        or ""
    ).strip()

    if range_header:
        request_headers["Range"] = range_header

    if_range = str(
        request.headers.get("If-Range")
        or ""
    ).strip()

    if if_range:
        request_headers["If-Range"] = if_range

    upstream = provider._request(
        "GET",
        remote_path,
        headers=request_headers,
        stream=True,
        allow_redirects=False,
    )

    if upstream.status_code == 404:
        upstream.close()
        raise Http404(
            "El vídeo no existe."
        )

    if upstream.status_code not in (
        200,
        206,
    ):
        status = upstream.status_code
        upstream.close()

        raise StorageProviderError(
            "El almacenamiento multimedia devolvió "
            f"HTTP {status}."
        )

    filename = (
        archivo.nombre_original
        or PurePosixPath(
            archivo.storage_key
        ).name
        or "video"
    )

    content_type = (
        upstream.headers.get(
            "Content-Type"
        )
        or archivo.mime_type
        or mimetypes.guess_type(
            filename
        )[0]
        or "application/octet-stream"
    )

    def content_iterator():
        try:
            for chunk in upstream.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    response = StreamingHttpResponse(
        content_iterator(),
        status=upstream.status_code,
        content_type=content_type,
    )

    for header_name in PASSTHROUGH_HEADERS:
        value = upstream.headers.get(
            header_name
        )

        if value:
            response[header_name] = value

    response["Accept-Ranges"] = (
        upstream.headers.get(
            "Accept-Ranges"
        )
        or "bytes"
    )

    response["Content-Disposition"] = (
        content_disposition_header(
            as_attachment=False,
            filename=filename,
        )
    )

    response["Cache-Control"] = (
        "private, no-store, max-age=0"
    )

    response["X-Content-Type-Options"] = (
        "nosniff"
    )

    return response
