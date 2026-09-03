from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .access import comparativas_access_required
from .forms import (
    ComparativaForm,
    BudgetV3ItemFormSet,
    BudgetV3ReviewForm,
    DocumentoComparativaForm,
    OfertaForm,
    OfertanteForm,
    PresupuestoImportConfirmForm,
    PresupuestoImportUploadForm,
)
from .integrations import (
    get_obras_options,
    get_proveedores_options,
    get_proveedores_options_for_team,
    get_team_scope,
    resolve_obra,
    resolve_proveedor,
    resolve_proveedor_for_team,
)
from .models import (
    Comparativa,
    DocumentoComparativa,
    Oferta,
    Ofertante,
)
from .services import (
    crear_oferta,
    guardar_documento,
)
from .document_intelligence_processing import (
    DOCUMENT_INTELLIGENCE_NAMESPACE,
    BudgetDocumentProcessingError,
    get_scoped_budget_document,
    procesar_documento_presupuesto,
)
from .document_intelligence_confirmation import (
    BudgetConfirmationError,
    build_budget_review_initial,
    confirm_budget_document,
    preview_requires_warning_acceptance,
)

from .presupuesto_import import (
    create_from_staged_budget,
    delete_staged_presupuesto,
    resolve_staged_presupuesto,
    save_staged_analysis,
    stage_presupuesto,
)


from .executive_ia import (
    ExecutiveIAError,
    prepare_executive_data,
    request_executive_report,
)


def _scope(request):
    return get_team_scope(request)


def _comparativa_visible(
    request,
    *,
    uid,
):
    team_scope, team, modo_todas = _scope(
        request
    )

    comparativa = get_object_or_404(
        Comparativa.objects.select_related(
            "team",
            "responsable",
            "creado_por",
        ),
        uuid=uid,
        team__in=team_scope,
    )

    return (
        comparativa,
        team_scope,
        team,
        modo_todas,
    )


@comparativas_access_required
def comparativas_list(request):
    team_scope, team, modo_todas = _scope(
        request
    )

    qs = (
        Comparativa.objects
        .filter(team__in=team_scope)
        .select_related(
            "team",
            "responsable",
        )
        .annotate(
            ofertantes_total=Count(
                "ofertantes",
                distinct=True,
            ),
            ofertas_total=Count(
                "ofertantes__ofertas",
                distinct=True,
            ),
        )
    )

    q = request.GET.get(
        "q",
        "",
    ).strip()

    estado = request.GET.get(
        "estado",
        "",
    ).strip()

    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(categoria__icontains=q)
            | Q(
                referencia_nombre__icontains=q
            )
            | Q(
                referencia_codigo__icontains=q
            )
        )

    if estado:
        qs = qs.filter(estado=estado)

    return render(
        request,
        "comparativas/list.html",
        {
            "comparativas": qs,
            "team": team,
            "team_scope": team_scope,
            "modo_todas": modo_todas,
            "q": q,
            "estado": estado,
            "estados": Comparativa.Estado.choices,
            "sin_team": not team_scope.exists(),
        },
    )


@comparativas_access_required
def comparativa_create(request):
    team_scope, team, modo_todas = _scope(
        request
    )

    obras = get_obras_options(team_scope)

    if request.method == "POST":
        form = ComparativaForm(
            request.POST,
            team_scope=team_scope,
            obras_options=obras,
        )

        if form.is_valid():
            selected_team = form.cleaned_data[
                "team"
            ]

            obra_ref = form.cleaned_data.get(
                "obra_ref"
            )

            obra = None

            if obra_ref:
                obra = resolve_obra(
                    team_scope,
                    obra_ref,
                )

                if (
                    not obra
                    or obra["team_id"]
                    != selected_team.pk
                ):
                    form.add_error(
                        "obra_ref",
                        (
                            "La obra no pertenece "
                            "a la empresa seleccionada."
                        ),
                    )

            if not form.errors:
                comparativa = form.save(
                    commit=False
                )

                comparativa.creado_por = (
                    request.user
                )
                comparativa.responsable = (
                    request.user
                )

                if obra:
                    comparativa.referencia_tipo = (
                        "planificacion_obra."
                        "ObraPlanificacion"
                    )
                    comparativa.referencia_id = str(
                        obra["id"]
                    )
                    comparativa.referencia_codigo = (
                        obra["codigo"]
                    )
                    comparativa.referencia_nombre = (
                        obra["nombre"]
                    )

                comparativa.save()

                messages.success(
                    request,
                    "Comparativa creada correctamente.",
                )

                return redirect(
                    "comparativas:detail",
                    uid=comparativa.uuid,
                )
    else:
        form = ComparativaForm(
            team_scope=team_scope,
            obras_options=obras,
            initial={
                "team": (
                    team.pk
                    if (
                        team is not None
                        and not modo_todas
                    )
                    else None
                ),
                "estado": (
                    Comparativa.Estado.BORRADOR
                ),
            },
        )

    return render(
        request,
        "comparativas/form.html",
        {
            "form": form,
            "team": team,
            "modo_todas": modo_todas,
            "sin_team": not team_scope.exists(),
        },
    )


# COMPARATIVAS_EDITAR_EXPEDIENTE_V1
@comparativas_access_required
def comparativa_update(request, uid):
    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    obras = get_obras_options(team_scope)

    original_team_id = comparativa.team_id

    obra_initial = ""

    if (
        comparativa.referencia_tipo
        == "planificacion_obra.ObraPlanificacion"
        and comparativa.referencia_id
    ):
        obra_initial = comparativa.referencia_id

    if request.method == "POST":
        form = ComparativaForm(
            request.POST,
            instance=comparativa,
            team_scope=team_scope,
            obras_options=obras,
        )

        if form.is_valid():
            selected_team = (
                form.cleaned_data["team"]
            )

            if (
                comparativa.ofertantes.exists()
                and selected_team.pk
                != original_team_id
            ):
                form.add_error(
                    "team",
                    (
                        "La empresa no puede cambiarse "
                        "una vez existen ofertantes."
                    ),
                )

            obra_ref = form.cleaned_data.get(
                "obra_ref"
            )

            obra = None

            if obra_ref:
                obra = resolve_obra(
                    team_scope,
                    obra_ref,
                )

                if (
                    not obra
                    or obra["team_id"]
                    != selected_team.pk
                ):
                    form.add_error(
                        "obra_ref",
                        (
                            "La obra no pertenece "
                            "a la empresa seleccionada."
                        ),
                    )

            if not form.errors:
                comparativa = form.save(
                    commit=False
                )

                if obra:
                    comparativa.referencia_tipo = (
                        "planificacion_obra."
                        "ObraPlanificacion"
                    )

                    comparativa.referencia_id = str(
                        obra["id"]
                    )

                    comparativa.referencia_codigo = (
                        obra["codigo"]
                    )

                    comparativa.referencia_nombre = (
                        obra["nombre"]
                    )
                else:
                    comparativa.referencia_tipo = ""
                    comparativa.referencia_id = ""
                    comparativa.referencia_codigo = ""
                    comparativa.referencia_nombre = ""

                comparativa.save()

                messages.success(
                    request,
                    (
                        "Comparativa actualizada "
                        "correctamente."
                    ),
                )

                return redirect(
                    "comparativas:detail",
                    uid=comparativa.uuid,
                )
    else:
        form = ComparativaForm(
            instance=comparativa,
            team_scope=team_scope,
            obras_options=obras,
            initial={
                "obra_ref": obra_initial,
            },
        )

    return render(
        request,
        "comparativas/form.html",
        {
            "form": form,
            "comparativa": comparativa,
            "team": team,
            "modo_todas": modo_todas,
            "sin_team": not team_scope.exists(),
        },
    )


@comparativas_access_required
def comparativa_detail(request, uid):
    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    ofertantes = (
        comparativa.ofertantes
        .prefetch_related(
            Prefetch(
                "ofertas",
                queryset=(
                    Oferta.objects
                    .prefetch_related(
                        "documentos",
                        "documentos__conceptos_extraidos",
                    )
                    .order_by(
                        "-version",
                        "-id",
                    )
                ),
            )
        )
        .order_by("nombre", "id")
    )

    return render(
        request,
        "comparativas/detail.html",
        {
            "comparativa": comparativa,
            "ofertantes": ofertantes,
            "team": team,
            "modo_todas": modo_todas,
        },
    )


# COMPARATIVAS_V2D_EXECUTIVE_IA_V1
@comparativas_access_required
def comparativa_executive_ia(
    request,
    uid,
):
    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    prepared = (
        prepare_executive_data(
            comparativa
        )
    )

    report = None
    report_rows = []
    option_name = ""
    ia_metadata = None
    ia_error = ""
    ia_error_code = ""

    if request.method == "POST":
        if not prepared[
            "can_generate"
        ]:
            ia_error = prepared[
                "blocking_reason"
            ]

        else:
            try:
                result = (
                    request_executive_report(
                        prepared=prepared,
                        user=request.user,
                        team=comparativa.team,
                    )
                )

            except ExecutiveIAError:
                ia_error = (
                    "No se ha podido validar "
                    "la comparativa generada."
                )

            except RuntimeError as exc:
                ia_error = (
                    "INTASA IA no ha podido "
                    "completar el análisis. "
                    "No se ha modificado "
                    "ningún dato."
                )

                ia_error_code = str(
                    getattr(
                        exc,
                        "code",
                        "",
                    )
                    or type(exc).__name__
                )

            else:
                report = result[
                    "datos"
                ]

                ia_metadata = {
                    "modelo": result.get(
                        "modelo"
                    ),
                    "request_id": result.get(
                        "request_id"
                    ),
                    "tokens_entrada": (
                        result.get(
                            "tokens_entrada"
                        )
                    ),
                    "tokens_salida": (
                        result.get(
                            "tokens_salida"
                        )
                    ),
                }

                analysis_by_id = {
                    int(
                        item[
                            "oferta_id"
                        ]
                    ): item
                    for item
                    in report[
                        "por_oferta"
                    ]
                }

                for row in prepared[
                    "rows"
                ]:
                    item = dict(row)

                    item["ia"] = (
                        analysis_by_id.get(
                            row[
                                "oferta_id"
                            ]
                        )
                    )

                    report_rows.append(
                        item
                    )

                option_id = int(
                    report[
                        "opcion_orientativa_oferta_id"
                    ]
                )

                if option_id:
                    for row in prepared[
                        "rows"
                    ]:
                        if (
                            row[
                                "oferta_id"
                            ]
                            == option_id
                        ):
                            option_name = (
                                row["nombre"]
                            )
                            break

    return render(
        request,
        "comparativas/executive_ia.html",
        {
            "comparativa": comparativa,
            "prepared": prepared,
            "rows": prepared["rows"],
            "report": report,
            "report_rows": (
                report_rows
            ),
            "option_name": (
                option_name
            ),
            "ia_metadata": (
                ia_metadata
            ),
            "ia_error": ia_error,
            "ia_error_code": (
                ia_error_code
            ),
            "team": team,
            "modo_todas": modo_todas,
        },
    )


# COMPARATIVAS_PRESUPUESTO_DOCUMENT_PREVIEW_V1
@comparativas_access_required
def presupuesto_import_document(request, uid):
    import mimetypes

    from django.http import (
        FileResponse,
        Http404,
    )

    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    token = (
        request.GET.get("token")
        or ""
    )

    if not token:
        raise Http404(
            "Documento temporal no disponible."
        )

    try:
        staged = (
            resolve_staged_presupuesto(
                token=token,
                user_id=request.user.pk,
                comparativa_uuid=(
                    comparativa.uuid
                ),
            )
        )
    except Exception:
        raise Http404(
            "Documento temporal no disponible."
        )

    extension = (
        staged.get("extension")
        or ""
    ).lower()

    safe_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }

    content_type = (
        safe_types.get(extension)
        or mimetypes.guess_type(
            staged.get(
                "original_name"
            )
            or ""
        )[0]
        or "application/octet-stream"
    )

    try:
        handle = staged["path"].open(
            "rb"
        )
    except OSError:
        raise Http404(
            "Documento temporal no disponible."
        )

    response = FileResponse(
        handle,
        as_attachment=False,
        filename=(
            staged.get(
                "original_name"
            )
            or "presupuesto"
        ),
        content_type=content_type,
    )

    response[
        "X-Content-Type-Options"
    ] = "nosniff"

    response[
        "Cache-Control"
    ] = "private, no-store"

    return response


# COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1
@comparativas_access_required
def presupuesto_import(request, uid):
    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    proveedores_options = (
        get_proveedores_options_for_team(
            comparativa.team_id
        )
    )

    upload_form = (
        PresupuestoImportUploadForm()
    )

    confirm_form = None
    analysis = None
    preview = False
    staged = None

    if request.method == "POST":
        action = request.POST.get(
            "action",
            "preview",
        )

        if action == "preview":
            upload_form = (
                PresupuestoImportUploadForm(
                    request.POST,
                    request.FILES,
                )
            )

            if upload_form.is_valid():
                try:
                    staged = stage_presupuesto(
                        uploaded_file=(
                            upload_form
                            .cleaned_data[
                                "archivo"
                            ]
                        ),
                        user_id=request.user.pk,
                        comparativa_uuid=(
                            comparativa.uuid
                        ),
                    )

                    # El staging ya no decide semántica ni economía.
                    # Solo conserva el binario hasta crear DocumentoComparativa
                    # y pasar por la revisión V3 explícita.
                    analysis = {
                        "method": "staged_v3_pending",
                        "text": "",
                        "text_len": 0,
                        "ocr_used": False,
                        "legacy_semantic_used": False,
                    }
                    save_staged_analysis(staged, analysis)

                    confirm_form = PresupuestoImportConfirmForm(
                        proveedores_options=proveedores_options,
                        initial={"token": staged["token"]},
                    )

                    preview = True

                except Exception as exc:
                    if staged:
                        delete_staged_presupuesto(
                            staged
                        )

                    upload_form.add_error(
                        "archivo",
                        (
                            "No se pudo analizar "
                            "el presupuesto: "
                            f"{exc}"
                        ),
                    )

        elif action == "confirm":
            confirm_form = (
                PresupuestoImportConfirmForm(
                    request.POST,
                    proveedores_options=(
                        proveedores_options
                    ),
                )
            )

            preview = True

            if confirm_form.is_valid():
                try:
                    staged = (
                        resolve_staged_presupuesto(
                            token=(
                                confirm_form
                                .cleaned_data[
                                    "token"
                                ]
                            ),
                            user_id=(
                                request.user.pk
                            ),
                            comparativa_uuid=(
                                comparativa.uuid
                            ),
                        )
                    )

                    analysis = (
                        staged.get(
                            "analysis"
                        )
                        or {}
                    )

                except Exception:
                    confirm_form.add_error(
                        None,
                        (
                            "La importación temporal "
                            "ha caducado o no es "
                            "válida. Vuelve a subir "
                            "el presupuesto."
                        ),
                    )

                if (
                    not confirm_form.errors
                    and staged
                ):
                    proveedor = None

                    proveedor_ref = (
                        confirm_form
                        .cleaned_data
                        .get(
                            "proveedor_ref"
                        )
                    )

                    if proveedor_ref:
                        proveedor = (
                            resolve_proveedor_for_team(
                                comparativa.team_id,
                                proveedor_ref,
                            )
                        )

                        if not proveedor:
                            confirm_form.add_error(
                                "proveedor_ref",
                                (
                                    "Proveedor no "
                                    "disponible para "
                                    "esta empresa."
                                ),
                            )

                    if not confirm_form.errors:
                        (
                            ofertante,
                            oferta,
                            documento,
                        ) = (
                            create_from_staged_budget(
                                comparativa=(
                                    comparativa
                                ),
                                provider=(
                                    proveedor
                                ),
                                cleaned_data=(
                                    confirm_form
                                    .cleaned_data
                                ),
                                staged=staged,
                                analysis=(
                                    analysis
                                ),
                                user=request.user,
                                v3_ingestion=True,
                            )
                        )

                        delete_staged_presupuesto(
                            staged
                        )

                        messages.success(
                            request,
                            (
                                "Presupuesto importado: "
                                f"{ofertante.nombre} · "
                                f"V{oferta.version}."
                            ),
                        )

                        return redirect(
                            "comparativas:documento_intelligence",
                            pk=documento.pk,
                        )

    top_match = None

    if analysis:
        matches = (
            analysis.get(
                "provider_matches"
            )
            or []
        )

        if matches:
            top_match = matches[0]

    staged_document = None

    if staged:
        try:
            size_bytes = (
                staged["path"]
                .stat()
                .st_size
            )
        except OSError:
            size_bytes = 0

        staged_document = {
            "original_name": (
                staged.get(
                    "original_name"
                )
                or "presupuesto"
            ),
            "extension": (
                staged.get(
                    "extension"
                )
                or ""
            ),
            "size_bytes": size_bytes,
            "token": (
                staged.get("token")
                or ""
            ),
        }

    return render(
        request,
        "comparativas/presupuesto_import.html",
        {
            "comparativa": comparativa,
            "upload_form": upload_form,
            "confirm_form": confirm_form,
            "analysis": analysis,
            "top_match": top_match,
            "preview": preview,
            "staged_document": (
                staged_document
            ),
        },
    )


@comparativas_access_required
def ofertante_create(request, uid):
    (
        comparativa,
        team_scope,
        team,
        modo_todas,
    ) = _comparativa_visible(
        request,
        uid=uid,
    )

    opciones = get_proveedores_options_for_team(
        comparativa.team_id
    )

    if request.method == "POST":
        form = OfertanteForm(
            request.POST,
            proveedores_options=opciones,
        )

        if form.is_valid():
            proveedor_ref = (
                form.cleaned_data.get(
                    "proveedor_ref"
                )
            )

            if proveedor_ref:
                proveedor = (
                    resolve_proveedor_for_team(
                        comparativa.team_id,
                        proveedor_ref,
                    )
                )

                if not proveedor:
                    form.add_error(
                        "proveedor_ref",
                        "Proveedor no disponible.",
                    )
                else:
                    Ofertante.objects.create(
                        comparativa=comparativa,
                        tipo=(
                            Ofertante.Tipo
                            .PROVEEDOR
                        ),
                        proveedor_ref_id=(
                            proveedor["id"]
                        ),
                        nombre=(
                            proveedor["nombre"]
                        ),
                        nif=proveedor["nif"],
                        email=proveedor["email"],
                        telefono=(
                            proveedor["telefono"]
                        ),
                    )

                    messages.success(
                        request,
                        "Proveedor añadido.",
                    )

                    return redirect(
                        "comparativas:detail",
                        uid=comparativa.uuid,
                    )
            else:
                Ofertante.objects.create(
                    comparativa=comparativa,
                    tipo=Ofertante.Tipo.CANDIDATO,
                    nombre=(
                        form.cleaned_data[
                            "nombre"
                        ].strip()
                    ),
                    nif=(
                        form.cleaned_data.get(
                            "nif"
                        )
                        or ""
                    ).strip(),
                    email=(
                        form.cleaned_data.get(
                            "email"
                        )
                        or ""
                    ).strip(),
                    telefono=(
                        form.cleaned_data.get(
                            "telefono"
                        )
                        or ""
                    ).strip(),
                )

                messages.success(
                    request,
                    "Candidato añadido.",
                )

                return redirect(
                    "comparativas:detail",
                    uid=comparativa.uuid,
                )
    else:
        form = OfertanteForm(
            proveedores_options=opciones,
        )

    return render(
        request,
        "comparativas/ofertante_form.html",
        {
            "comparativa": comparativa,
            "form": form,
        },
    )


@comparativas_access_required
def oferta_create(request, pk):
    team_scope, team, modo_todas = _scope(
        request
    )

    ofertante = get_object_or_404(
        Ofertante.objects.select_related(
            "comparativa"
        ),
        pk=pk,
        comparativa__team__in=team_scope,
    )

    if request.method == "POST":
        form = OfertaForm(request.POST)

        if form.is_valid():
            oferta = crear_oferta(
                ofertante=ofertante,
                cleaned_data=form.cleaned_data,
                user=request.user,
            )

            messages.success(
                request,
                (
                    "Oferta "
                    f"V{oferta.version} creada."
                ),
            )

            return redirect("comparativas:documento_upload", pk=oferta.pk)
    else:
        form = OfertaForm()

    return render(
        request,
        "comparativas/oferta_form.html",
        {
            "ofertante": ofertante,
            "comparativa": (
                ofertante.comparativa
            ),
            "form": form,
        },
    )


@comparativas_access_required
def oferta_delete(request, pk):
    """
    Eliminación explícita de una única versión/oferta.

    No elimina el ofertante ni renumera las restantes
    versiones.
    """
    from django.core.exceptions import PermissionDenied
    from django.http import HttpResponseNotAllowed

    from .version_delete import delete_offer_version

    if request.method != "POST":
        return HttpResponseNotAllowed(
            ["POST"]
        )

    if not request.user.has_perm(
        "comparativas.delete_oferta"
    ):
        raise PermissionDenied

    team_scope, _team, _modo_todas = _scope(
        request
    )

    oferta = get_object_or_404(
        Oferta.objects.select_related(
            "ofertante__comparativa"
        ),
        pk=pk,
        ofertante__comparativa__team__in=(
            team_scope
        ),
    )

    comparativa = (
        oferta.ofertante.comparativa
    )

    result = delete_offer_version(
        oferta=oferta,
        user=request.user,
    )

    messages.success(
        request,
        (
            f"Versión {result['version']} eliminada. "
            f"Se eliminaron "
            f"{result['documentos']} documento(s) "
            f"y {result['conceptos']} concepto(s). "
            "El ofertante y las demás versiones "
            "se conservan."
        ),
    )

    return redirect(
        "comparativas:detail",
        uid=comparativa.uuid,
    )


@comparativas_access_required
def documento_upload(request, pk):
    team_scope, team, modo_todas = _scope(
        request
    )

    oferta = get_object_or_404(
        Oferta.objects.select_related(
            "ofertante__comparativa"
        ),
        pk=pk,
        ofertante__comparativa__team__in=(
            team_scope
        ),
    )

    if request.method == "POST":
        form = DocumentoComparativaForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            documento, creado = (
                guardar_documento(
                    oferta=oferta,
                    uploaded_file=(
                        form.cleaned_data[
                            "archivo"
                        ]
                    ),
                    user=request.user,
                )
            )

            if creado:
                messages.success(
                    request,
                    (
                        "Documento guardado. "
                        "Puede analizarlo explícitamente con "
                        "INTASA IA desde la comparativa."
                    ),
                )
            else:
                messages.info(
                    request,
                    (
                        "Ese documento ya estaba "
                        "adjunto a esta oferta."
                    ),
                )

            return redirect("comparativas:documento_intelligence", pk=documento.pk)
    else:
        form = DocumentoComparativaForm()

    return render(
        request,
        "comparativas/documento_form.html",
        {
            "form": form,
            "oferta": oferta,
            "ofertante": oferta.ofertante,
            "comparativa": (
                oferta
                .ofertante
                .comparativa
            ),
        },
    )


@comparativas_access_required
def documento_view(request, pk):
    team_scope, team, modo_todas = _scope(
        request
    )

    documento = get_object_or_404(
        DocumentoComparativa.objects
        .select_related(
            "oferta__ofertante__comparativa"
        ),
        pk=pk,
        oferta__ofertante__comparativa__team__in=(
            team_scope
        ),
    )

    if not documento.archivo:
        raise Http404

    try:
        handle = documento.archivo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404

    return FileResponse(
        handle,
        content_type=(
            documento.content_type
            or "application/octet-stream"
        ),
        as_attachment=False,
        filename=documento.nombre_original,
    )


def _document_intelligence_context(
    documento,
    *,
    header_form=None,
    item_formset=None,
):
    namespace = (
        (documento.datos_extraidos or {}).get(
            DOCUMENT_INTELLIGENCE_NAMESPACE
        )
        or {}
    )
    preview = namespace.get("preview") or {}
    validation = namespace.get("validation") or {}
    item_checks = {
        item.get("index"): item
        for item in validation.get("partidas") or []
    }
    partidas = []
    for index, item in enumerate(preview.get("partidas") or []):
        row = dict(item)
        check = item_checks.get(index) or {}
        arithmetic = check.get("arithmetic") or {}
        row["validation_status"] = arithmetic.get("status") or "NOT_EVALUABLE"
        row["validation_difference"] = arithmetic.get("difference")
        partidas.append(row)
    return {
        "documento": documento,
        "oferta": documento.oferta,
        "ofertante": documento.oferta.ofertante,
        "comparativa": documento.oferta.ofertante.comparativa,
        "v3": namespace,
        "preview": preview,
        "validation": validation,
        "partidas": partidas,
        "header_form": header_form,
        "item_formset": item_formset,
        "has_existing_concepts": documento.conceptos_extraidos.exists(),
    }


@comparativas_access_required
def documento_intelligence(request, pk):
    team_scope, _team, _modo_todas = _scope(request)
    documento = get_scoped_budget_document(
        document_id=pk,
        team_scope=team_scope,
    )

    namespace = (
        (documento.datos_extraidos or {}).get(
            DOCUMENT_INTELLIGENCE_NAMESPACE
        )
        or {}
    )

    if request.method == "POST":
        action = str(request.POST.get("action") or "")
        if action == "confirm":
            options = get_proveedores_options_for_team(
                documento.oferta.ofertante.comparativa.team_id
            )
            header_form = BudgetV3ReviewForm(
                request.POST,
                proveedores_options=options,
                requires_warning_acceptance=preview_requires_warning_acceptance(namespace),
            )
            expected_count = len((namespace.get("preview") or {}).get("partidas") or [])
            item_formset = BudgetV3ItemFormSet(
                request.POST,
                prefix="partidas",
                expected_count=expected_count,
            )
            if header_form.is_valid() and item_formset.is_valid():
                try:
                    result = confirm_budget_document(
                        pk,
                        user=request.user,
                        team_scope=team_scope,
                        header=header_form.cleaned_data,
                        reviewed_rows=[form.cleaned_data for form in item_formset.forms],
                    )
                    if result["reused"]:
                        messages.info(request, "El presupuesto ya estaba confirmado con esta misma revisión.")
                    else:
                        messages.success(request, "Presupuesto confirmado.")
                    return redirect(
                        "comparativas:detail",
                        uid=documento.oferta.ofertante.comparativa.uuid,
                    )
                except BudgetConfirmationError as exc:
                    header_form.add_error(None, f"No se puede confirmar el presupuesto ({exc.code}).")
            return render(
                request,
                "comparativas/document_intelligence.html",
                _document_intelligence_context(
                    documento,
                    header_form=header_form,
                    item_formset=item_formset,
                ),
            )

        if action not in {"analyze", "reanalyze"}:
            messages.error(request, "Acción de análisis no válida.")
        else:
            try:
                result = procesar_documento_presupuesto(
                    pk,
                    user=request.user,
                    team_scope=team_scope,
                    force=action == "reanalyze",
                )
                if result["status"] == "PROCESANDO":
                    messages.info(request, "El documento ya se está procesando.")
                elif result["reused"]:
                    messages.info(
                        request,
                        "Se reutilizó el análisis vigente; no se realizó otra llamada IA.",
                    )
                else:
                    messages.success(
                        request,
                        "Análisis INTASA IA V3 completado. Revise la propuesta antes de confirmar datos.",
                    )
            except BudgetDocumentProcessingError as exc:
                messages.error(
                    request,
                    f"No se pudo completar el análisis ({exc.code}).",
                )
        return redirect("comparativas:documento_intelligence", pk=pk)

    namespace = (
        (documento.datos_extraidos or {}).get(
            DOCUMENT_INTELLIGENCE_NAMESPACE
        )
        or {}
    )
    header_form = None
    item_formset = None
    if namespace.get("status") == "COMPLETADO":
        initial_header, initial_items = build_budget_review_initial(documento)
        header_form = BudgetV3ReviewForm(
            initial=initial_header,
            proveedores_options=get_proveedores_options_for_team(
                documento.oferta.ofertante.comparativa.team_id
            ),
            requires_warning_acceptance=preview_requires_warning_acceptance(namespace),
        )
        item_formset = BudgetV3ItemFormSet(
            initial=initial_items,
            prefix="partidas",
            expected_count=len(initial_items),
        )
    return render(
        request,
        "comparativas/document_intelligence.html",
        _document_intelligence_context(
            documento,
            header_form=header_form,
            item_formset=item_formset,
        ),
    )



# COMPARATIVAS_V2C_PREVIEW_CONFIRM_R1

@comparativas_access_required
def documento_conceptos(
    request,
    pk,
):
    from django.contrib import messages
    from django.shortcuts import (
        get_object_or_404,
        redirect,
        render,
    )

    from .concept_extraction import (
        extract_concepts_preview,
    )
    from .concept_review import (
        ConceptosYaConfirmados,
        build_review_initial,
        confirm_document_concepts,
    )
    from .forms import (
        ConceptoPreviewFormSet,
    )
    from .models import (
        DocumentoComparativa,
    )

    (
        team_scope,
        team,
        modo_todas,
    ) = _scope(
        request
    )

    documento = get_object_or_404(
        DocumentoComparativa.objects
        .select_related(
            "oferta",
            "oferta__ofertante",
            (
                "oferta__ofertante"
                "__comparativa"
            ),
        )
        .prefetch_related(
            "conceptos_extraidos",
        ),
        pk=pk,
        oferta__ofertante__comparativa__team__in=(
            team_scope
        ),
    )

    oferta = documento.oferta
    ofertante = oferta.ofertante
    comparativa = (
        ofertante.comparativa
    )

    persisted = list(
        documento
        .conceptos_extraidos
        .order_by(
            "orden",
            "id",
        )
    )

    if persisted:
        datos = (
            documento.datos_extraidos
            or {}
        )

        return render(
            request,
            (
                "comparativas/"
                "conceptos_review.html"
            ),
            {
                "comparativa": (
                    comparativa
                ),
                "ofertante": ofertante,
                "oferta": oferta,
                "documento": documento,
                "confirmed": True,
                "persisted_concepts": (
                    persisted
                ),
                "saved_summary": (
                    datos.get(
                        "conceptos_v2c"
                    )
                    or {}
                ),
            },
        )

    pdf_path = None

    if (
        documento.extension
        .lower()
        == ".pdf"
        and documento.archivo
    ):
        try:
            pdf_path = (
                documento.archivo.path
            )
        except (
            AttributeError,
            NotImplementedError,
            ValueError,
        ):
            pdf_path = None

    preview = (
        extract_concepts_preview(
            text=(
                documento.texto_extraido
                or ""
            ),
            base=oferta.base,
            pdf_path=pdf_path,
        )
    )

    preview_concepts = (
        preview.get(
            "conceptos"
        )
        or []
    )

    initial = (
        build_review_initial(
            preview_concepts
        )
    )

    if request.method == "POST":
        formset = (
            ConceptoPreviewFormSet(
                request.POST,
                prefix="concepts",
                expected_count=(
                    len(
                        preview_concepts
                    )
                ),
            )
        )

        if formset.is_valid():
            reviewed_rows = []

            for form in (
                formset.forms
            ):
                cleaned = (
                    form.cleaned_data
                )

                if not cleaned.get(
                    "selected"
                ):
                    continue

                reviewed_rows.append({
                    "source_index": (
                        cleaned[
                            "source_index"
                        ]
                    ),
                    "titulo": (
                        cleaned[
                            "titulo"
                        ]
                    ),
                    "descripcion": (
                        cleaned.get(
                            "descripcion"
                        )
                        or ""
                    ),
                    "cantidad": (
                        cleaned.get(
                            "cantidad"
                        )
                    ),
                    "unidad": (
                        cleaned.get(
                            "unidad"
                        )
                        or ""
                    ),
                    "precio_unitario": (
                        cleaned.get(
                            "precio_unitario"
                        )
                    ),
                    "importe": (
                        cleaned.get(
                            "importe"
                        )
                    ),
                    "alcance": (
                        cleaned[
                            "alcance"
                        ]
                    ),
                })

            try:
                created = (
                    confirm_document_concepts(
                        documento_id=(
                            documento.pk
                        ),
                        preview=preview,
                        reviewed_rows=(
                            reviewed_rows
                        ),
                        user=request.user,
                    )
                )

            except ConceptosYaConfirmados:
                messages.info(
                    request,
                    (
                        "Los conceptos de este "
                        "documento ya estaban "
                        "confirmados."
                    ),
                )

                return redirect(
                    "comparativas:documento_conceptos",
                    pk=documento.pk,
                )

            messages.success(
                request,
                (
                    f"{len(created)} conceptos "
                    "confirmados para "
                    f"{ofertante.nombre} · "
                    f"V{oferta.version}."
                ),
            )

            return redirect(
                "comparativas:detail",
                uid=(
                    comparativa.uuid
                ),
            )

    else:
        formset = (
            ConceptoPreviewFormSet(
                initial=initial,
                prefix="concepts",
                expected_count=(
                    len(
                        preview_concepts
                    )
                ),
            )
        )

    review_rows = []

    for index, form in enumerate(
        formset.forms
    ):
        source_item = {}

        if (
            index
            < len(
                preview_concepts
            )
        ):
            source_item = (
                preview_concepts[
                    index
                ]
            )

        review_rows.append({
            "form": form,
            "source": source_item,
        })

    return render(
        request,
        (
            "comparativas/"
            "conceptos_review.html"
        ),
        {
            "comparativa": comparativa,
            "ofertante": ofertante,
            "oferta": oferta,
            "documento": documento,
            "confirmed": False,
            "preview": preview,
            "reconciliation": (
                preview.get(
                    "reconciliacion"
                )
                or {}
            ),
            "review_rows": (
                review_rows
            ),
            "formset": formset,
            "can_confirm": bool(
                preview_concepts
            ),
        },
    )


# COMPARATIVAS_V2C_EDIT_CONFIRMED_CONCEPTS_R1

@comparativas_access_required
def documento_conceptos_editar(
    request,
    pk,
):
    from django.contrib import messages
    from django.shortcuts import (
        get_object_or_404,
        redirect,
        render,
    )

    from .concept_review import (
        ConceptosConRelaciones,
        build_persisted_edit_initial,
        update_confirmed_concepts,
    )
    from .forms import (
        ConceptoConfirmedEditFormSet,
    )
    from .models import (
        DocumentoComparativa,
    )

    (
        team_scope,
        team,
        modo_todas,
    ) = _scope(
        request
    )

    documento = get_object_or_404(
        DocumentoComparativa.objects
        .select_related(
            "oferta",
            "oferta__ofertante",
            (
                "oferta__ofertante"
                "__comparativa"
            ),
        )
        .prefetch_related(
            "conceptos_extraidos",
            (
                "conceptos_extraidos"
                "__relaciones_comparacion"
            ),
        ),
        pk=pk,
        oferta__ofertante__comparativa__team__in=(
            team_scope
        ),
    )

    oferta = documento.oferta
    ofertante = oferta.ofertante
    comparativa = (
        ofertante.comparativa
    )

    concepts = list(
        documento.conceptos_extraidos
        .order_by(
            "orden",
            "id",
        )
    )

    if not concepts:
        messages.info(
            request,
            (
                "Este documento todavía no "
                "tiene conceptos confirmados."
            ),
        )

        return redirect(
            "comparativas:documento_conceptos",
            pk=documento.pk,
        )

    if any(
        item.relaciones_comparacion.exists()
        for item in concepts
    ):
        messages.warning(
            request,
            (
                "Los conceptos ya tienen "
                "relaciones de comparación. "
                "Revísalas antes de modificar "
                "los conceptos fuente."
            ),
        )

        return redirect(
            "comparativas:documento_conceptos",
            pk=documento.pk,
        )

    expected_ids = [
        item.pk
        for item in concepts
    ]

    if request.method == "POST":
        formset = (
            ConceptoConfirmedEditFormSet(
                request.POST,
                prefix="edit",
                expected_ids=(
                    expected_ids
                ),
            )
        )

        if formset.is_valid():
            reviewed_rows = [
                {
                    "concept_id": (
                        form.cleaned_data[
                            "concept_id"
                        ]
                    ),
                    "titulo": (
                        form.cleaned_data[
                            "titulo"
                        ]
                    ),
                    "descripcion": (
                        form.cleaned_data.get(
                            "descripcion"
                        )
                        or ""
                    ),
                    "cantidad": (
                        form.cleaned_data.get(
                            "cantidad"
                        )
                    ),
                    "unidad": (
                        form.cleaned_data.get(
                            "unidad"
                        )
                        or ""
                    ),
                    "precio_unitario": (
                        form.cleaned_data.get(
                            "precio_unitario"
                        )
                    ),
                    "importe": (
                        form.cleaned_data.get(
                            "importe"
                        )
                    ),
                    "alcance": (
                        form.cleaned_data[
                            "alcance"
                        ]
                    ),
                }
                for form in formset.forms
            ]

            try:
                result = (
                    update_confirmed_concepts(
                        documento_id=(
                            documento.pk
                        ),
                        reviewed_rows=(
                            reviewed_rows
                        ),
                        user=request.user,
                    )
                )

            except ConceptosConRelaciones:
                messages.warning(
                    request,
                    (
                        "Los conceptos ya tienen "
                        "relaciones de comparación "
                        "y no pueden editarse "
                        "desde esta pantalla."
                    ),
                )

                return redirect(
                    "comparativas:documento_conceptos",
                    pk=documento.pk,
                )

            if (
                result[
                    "changed_count"
                ]
            ):
                messages.success(
                    request,
                    (
                        f"{result['changed_count']} "
                        "concepto(s) actualizado(s). "
                        "La evidencia original "
                        "se ha conservado."
                    ),
                )
            else:
                messages.info(
                    request,
                    "No había cambios que guardar.",
                )

            return redirect(
                "comparativas:documento_conceptos",
                pk=documento.pk,
            )

    else:
        formset = (
            ConceptoConfirmedEditFormSet(
                initial=(
                    build_persisted_edit_initial(
                        concepts
                    )
                ),
                prefix="edit",
                expected_ids=(
                    expected_ids
                ),
            )
        )

    rows = [
        {
            "form": form,
            "concepto": concepto,
        }
        for form, concepto
        in zip(
            formset.forms,
            concepts,
        )
    ]

    return render(
        request,
        (
            "comparativas/"
            "conceptos_edit.html"
        ),
        {
            "comparativa": comparativa,
            "ofertante": ofertante,
            "oferta": oferta,
            "documento": documento,
            "formset": formset,
            "rows": rows,
        },
    )
