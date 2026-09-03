from pathlib import Path

from django import forms

from .models import (
    Comparativa,
    ConceptoOferta,
    Oferta,
)


ACCEPTED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".odt",
    ".ods",
    ".txt",
}

MAX_DOCUMENT_SIZE = 25 * 1024 * 1024


def _bootstrap_fields(form):
    for field in form.fields.values():
        widget = field.widget

        if isinstance(
            widget,
            forms.CheckboxInput,
        ):
            css = "form-check-input"
        else:
            css = "form-control"

            if isinstance(
                widget,
                forms.Select,
            ):
                css = "form-select"

        current = widget.attrs.get(
            "class",
            "",
        )

        widget.attrs["class"] = (
            f"{current} {css}"
        ).strip()


# COMPARATIVAS_MULTIEMPRESA_OBRA_SELECTOR_V1
class TeamScopedObraSelect(forms.Select):
    """
    Expone el Team de cada obra como data-team-id.

    La interfaz filtra las opciones por empresa.
    La validación de seguridad definitiva permanece
    también en servidor.
    """

    def __init__(
        self,
        *args,
        obra_team_map=None,
        **kwargs,
    ):
        self.obra_team_map = {
            str(key): str(value)
            for key, value in (
                obra_team_map or {}
            ).items()
        }

        super().__init__(*args, **kwargs)

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )

        raw_value = str(
            option.get("value") or ""
        )

        team_id = self.obra_team_map.get(
            raw_value
        )

        if team_id:
            option.setdefault(
                "attrs",
                {},
            )["data-team-id"] = team_id

        return option


class ComparativaForm(forms.ModelForm):
    obra_ref = forms.ChoiceField(
        required=False,
        label="Obra / proyecto",
    )

    class Meta:
        model = Comparativa
        fields = (
            "team",
            "titulo",
            "categoria",
            "estado",
            "descripcion",
        )
        labels = {
            "team": "Empresa",
            "titulo": "Nombre de la comparativa",
            "categoria": "Especialidad / categoría",
            "estado": "Estado",
            "descripcion": "Alcance a comparar",
        }
        widgets = {
            "descripcion": forms.Textarea(
                attrs={"rows": 5}
            ),
        }

    def __init__(
        self,
        *args,
        team_scope=None,
        obras_options=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # MULTIEMPRESA:
        # si existen varias empresas no se asume
        # silenciosamente la primera.
        self.fields["team"].empty_label = (
            "Selecciona empresa"
        )

        if team_scope is not None:
            self.fields["team"].queryset = (
                team_scope.order_by("name", "id")
            )

        choices = [
            (
                "",
                "Selecciona primero una empresa",
            ),
        ]

        obra_team_map = {}

        for item in obras_options or []:
            obra_id = str(item["id"])

            choices.append(
                (
                    obra_id,
                    item["label"],
                )
            )

            obra_team_map[obra_id] = str(
                item["team_id"]
            )

        obra_field = self.fields["obra_ref"]

        # El widget debe instalarse ANTES de asignar choices.
        obra_field.widget = TeamScopedObraSelect(
            obra_team_map=obra_team_map,
        )

        obra_field.choices = choices

        obra_field.widget.attrs[
            "data-comparativas-obra-selector"
        ] = "v1"

        _bootstrap_fields(self)


class OfertanteForm(forms.Form):
    proveedor_ref = forms.ChoiceField(
        required=False,
        label="Proveedor existente",
    )

    nombre = forms.CharField(
        required=False,
        max_length=255,
        label="Nombre del candidato",
    )

    nif = forms.CharField(
        required=False,
        max_length=60,
        label="NIF / CIF",
    )

    email = forms.EmailField(
        required=False,
    )

    telefono = forms.CharField(
        required=False,
        max_length=80,
    )

    def __init__(
        self,
        *args,
        proveedores_options=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        choices = [
            (
                "",
                "No está todavía en Proveedores",
            ),
        ]

        for item in proveedores_options or []:
            choices.append(
                (
                    str(item["id"]),
                    item["label"],
                )
            )

        self.fields[
            "proveedor_ref"
        ].choices = choices

        _bootstrap_fields(self)

    def clean(self):
        cleaned = super().clean()

        if not cleaned.get(
            "proveedor_ref"
        ) and not (
            cleaned.get("nombre") or ""
        ).strip():
            self.add_error(
                "nombre",
                (
                    "Selecciona un proveedor "
                    "o indica el nombre del candidato."
                ),
            )

        return cleaned


class OfertaForm(forms.ModelForm):
    class Meta:
        model = Oferta
        fields = (
            "fecha_documento",
            "referencia",
            "base",
            "impuestos",
            "total",
            "observaciones",
        )
        labels = {
            "fecha_documento": "Fecha del presupuesto",
            "referencia": "Nº / referencia",
            "base": "Base imponible",
            "impuestos": "Impuestos",
            "total": "Total",
            "observaciones": "Observaciones",
        }
        widgets = {
            "fecha_documento": forms.DateInput(
                attrs={"type": "date"}
            ),
            "observaciones": forms.Textarea(
                attrs={"rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        _bootstrap_fields(self)


class DocumentoComparativaForm(forms.Form):
    archivo = forms.FileField(
        label="Documento",
        help_text=(
            "PDF, imagen, Word, Excel/OpenDocument "
            "o TXT. Máximo 25 MB."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap_fields(self)

        self.fields[
            "archivo"
        ].widget.attrs["accept"] = (
            ".pdf,.jpg,.jpeg,.png,.webp,"
            ".tif,.tiff,.doc,.docx,.xls,.xlsx,"
            ".odt,.ods,.txt"
        )

    def clean_archivo(self):
        archivo = self.cleaned_data[
            "archivo"
        ]

        extension = Path(
            archivo.name or ""
        ).suffix.lower()

        if extension not in ACCEPTED_EXTENSIONS:
            raise forms.ValidationError(
                "Tipo de archivo no permitido."
            )

        if archivo.size > MAX_DOCUMENT_SIZE:
            raise forms.ValidationError(
                "El documento supera los 25 MB."
            )

        return archivo


# COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1

PRESUPUESTO_IMPORT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
}

PRESUPUESTO_IMPORT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/tiff",
    "application/octet-stream",
}


class PresupuestoImportUploadForm(
    forms.Form
):
    archivo = forms.FileField(
        label="Presupuesto",
        help_text=(
            "PDF o imagen. "
            "Máximo 25 MB."
        ),
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        _bootstrap_fields(self)

        self.fields[
            "archivo"
        ].widget.attrs["accept"] = (
            ".pdf,.jpg,.jpeg,.png,"
            ".webp,.tif,.tiff"
        )

    def clean_archivo(self):
        archivo = (
            self.cleaned_data[
                "archivo"
            ]
        )

        extension = Path(
            archivo.name or ""
        ).suffix.lower()

        if (
            extension
            not in PRESUPUESTO_IMPORT_EXTENSIONS
        ):
            raise forms.ValidationError(
                "Solo se permiten PDF "
                "o imágenes."
            )

        if (
            archivo.size
            > MAX_DOCUMENT_SIZE
        ):
            raise forms.ValidationError(
                "El documento supera "
                "los 25 MB."
            )

        content_type = (
            getattr(
                archivo,
                "content_type",
                "",
            )
            or ""
        ).split(";")[0].lower()

        if (
            content_type
            and content_type
            not in PRESUPUESTO_IMPORT_MIME_TYPES
        ):
            raise forms.ValidationError(
                "El tipo MIME del archivo "
                "no es válido."
            )

        try:
            if extension == ".pdf":
                signature = archivo.read(5)
                archivo.seek(0)

                if signature != b"%PDF-":
                    raise forms.ValidationError(
                        "El archivo no parece "
                        "un PDF válido."
                    )
            else:
                from PIL import Image

                Image.open(
                    archivo
                ).verify()

                archivo.seek(0)

        except forms.ValidationError:
            raise
        except Exception:
            try:
                archivo.seek(0)
            except Exception:
                pass

            raise forms.ValidationError(
                "La imagen no se puede "
                "validar."
            )

        return archivo


class PresupuestoImportConfirmForm(
    forms.Form
):
    token = forms.CharField(
        widget=forms.HiddenInput,
    )

    proveedor_ref = (
        forms.ChoiceField(
            required=False,
            label=(
                "Proveedor existente"
            ),
        )
    )

    nombre = forms.CharField(
        required=False,
        max_length=255,
        label=(
            "Nombre del ofertante"
        ),
    )

    nif = forms.CharField(
        required=False,
        max_length=60,
        label="NIF / CIF",
    )

    fecha_documento = (
        forms.DateField(
            required=False,
            label=(
                "Fecha del presupuesto"
            ),
            widget=forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        )
    )

    referencia = forms.CharField(
        required=False,
        max_length=120,
        label="Nº / referencia",
    )

    base = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        label="Base imponible",
    )

    impuestos = (
        forms.DecimalField(
            required=False,
            max_digits=14,
            decimal_places=2,
            label="Impuestos / IVA",
        )
    )

    total = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        label="Total",
    )

    observaciones = forms.CharField(
        required=False,
        label="Observaciones",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    def __init__(
        self,
        *args,
        proveedores_options=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        choices = [
            (
                "",
                (
                    "No vincular a proveedor "
                    "existente"
                ),
            )
        ]

        for item in (
            proveedores_options or []
        ):
            choices.append(
                (
                    str(item["id"]),
                    item["label"],
                )
            )

        self.fields[
            "proveedor_ref"
        ].choices = choices

        _bootstrap_fields(self)

    def clean(self):
        cleaned = super().clean()

        if (
            not cleaned.get(
                "proveedor_ref"
            )
            and not (
                cleaned.get("nombre")
                or ""
            ).strip()
        ):
            self.add_error(
                "nombre",
                (
                    "Selecciona un proveedor "
                    "o confirma el nombre "
                    "del candidato."
                ),
            )

        return cleaned



# COMPARATIVAS_V2C_PREVIEW_CONFIRM_R1


class ConceptoPreviewForm(
    forms.Form
):
    selected = forms.BooleanField(
        required=False,
        initial=True,
        label="Incluir",
    )

    source_index = forms.IntegerField(
        min_value=0,
        widget=forms.HiddenInput,
    )

    titulo = forms.CharField(
        max_length=500,
        label="Concepto",
    )

    descripcion = forms.CharField(
        required=False,
        label="Descripción",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
            }
        ),
    )

    cantidad = forms.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=4,
        label="Cantidad",
    )

    unidad = forms.CharField(
        required=False,
        max_length=40,
        label="Unidad",
    )

    precio_unitario = (
        forms.DecimalField(
            required=False,
            max_digits=18,
            decimal_places=4,
            label="Precio unitario",
        )
    )

    importe = forms.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=2,
        label="Importe",
    )

    alcance = forms.ChoiceField(
        choices=(
            ConceptoOferta
            .Alcance
            .choices
        ),
        label="Alcance",
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        _bootstrap_fields(
            self
        )


class BaseConceptoPreviewFormSet(
    forms.BaseFormSet
):
    def __init__(
        self,
        *args,
        expected_count=None,
        **kwargs,
    ):
        self.expected_count = (
            expected_count
        )

        super().__init__(
            *args,
            **kwargs,
        )

    def clean(self):
        super().clean()

        if any(
            self.errors
        ):
            return

        indices = []

        selected = 0

        for form in self.forms:
            data = (
                form.cleaned_data
                or {}
            )

            indices.append(
                data.get(
                    "source_index"
                )
            )

            if data.get(
                "selected"
            ):
                selected += 1

        if (
            self.expected_count
            is not None
        ):
            expected = set(
                range(
                    self.expected_count
                )
            )

            received = set(
                indices
            )

            if (
                len(indices)
                != self.expected_count
                or received
                != expected
            ):
                raise forms.ValidationError(
                    (
                        "La previsualización ha "
                        "cambiado o no es válida. "
                        "Vuelve a cargarla antes "
                        "de confirmar."
                    )
                )

        if selected == 0:
            raise forms.ValidationError(
                (
                    "Selecciona al menos "
                    "un concepto para confirmar."
                )
            )


ConceptoPreviewFormSet = (
    forms.formset_factory(
        ConceptoPreviewForm,
        formset=(
            BaseConceptoPreviewFormSet
        ),
        extra=0,
        max_num=200,
        validate_max=True,
    )
)


# DOCUMENT INTELLIGENCE V3 · revisión humana canónica
class BudgetV3ReviewForm(forms.Form):
    preview_fingerprint = forms.CharField(widget=forms.HiddenInput)
    document_sha256 = forms.CharField(widget=forms.HiddenInput)
    proveedor_ref = forms.ChoiceField(
        required=False,
        label="Proveedor maestro propuesto",
    )
    confirmar_vinculo_proveedor = forms.BooleanField(
        required=False,
        label="Confirmo expresamente la vinculación con este proveedor maestro",
    )
    proveedor_emisor = forms.CharField(max_length=500, label="Proveedor / emisor")
    proveedor_nif_cif = forms.CharField(required=False, max_length=80, label="NIF / CIF del emisor")
    numero = forms.CharField(required=False, max_length=160, label="Nº / referencia")
    fecha = forms.DateField(
        required=False,
        label="Fecha del presupuesto",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    cliente_nombre = forms.CharField(required=False, max_length=500, label="Cliente")
    cliente_nif_cif = forms.CharField(required=False, max_length=80, label="NIF / CIF del cliente")
    cliente_direccion = forms.CharField(
        required=False,
        max_length=1000,
        label="Dirección del cliente",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    base = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=0, label="Base")
    iva = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=0, label="IVA")
    total = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=0, label="Total")
    moneda = forms.CharField(required=False, max_length=3, label="Moneda")
    forma_pago = forms.CharField(required=False, max_length=500, label="Forma de pago")
    validez = forms.CharField(required=False, max_length=300, label="Validez")
    plazo = forms.CharField(required=False, max_length=300, label="Plazo")
    portes = forms.CharField(required=False, max_length=500, label="Portes")
    observaciones = forms.CharField(
        required=False,
        max_length=2000,
        label="Observaciones",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    aceptar_advertencias = forms.BooleanField(
        required=False,
        label="He revisado y acepto las advertencias y discrepancias mostradas",
    )
    reemplazar_conceptos = forms.BooleanField(
        required=False,
        label="Confirmo que deseo reemplazar los conceptos existentes de este documento",
    )

    def __init__(self, *args, proveedores_options=None, requires_warning_acceptance=False, **kwargs):
        self.requires_warning_acceptance = bool(requires_warning_acceptance)
        super().__init__(*args, **kwargs)
        choices = [("", "No vincular a proveedor maestro")]
        choices.extend(
            (str(item["id"]), item["label"])
            for item in (proveedores_options or [])
        )
        self.fields["proveedor_ref"].choices = choices
        _bootstrap_fields(self)

    def clean(self):
        cleaned = super().clean()
        provider_ref = cleaned.get("proveedor_ref")
        confirm_link = cleaned.get("confirmar_vinculo_proveedor")
        if provider_ref and not confirm_link:
            self.add_error(
                "confirmar_vinculo_proveedor",
                "La vinculación con un proveedor maestro requiere confirmación expresa.",
            )
        if confirm_link and not provider_ref:
            self.add_error(
                "proveedor_ref",
                "Selecciona el proveedor maestro que deseas vincular.",
            )
        if self.requires_warning_acceptance and not cleaned.get("aceptar_advertencias"):
            self.add_error(
                "aceptar_advertencias",
                "Debe revisar y aceptar las advertencias antes de confirmar.",
            )
        return cleaned


class BudgetV3ItemForm(forms.Form):
    selected = forms.BooleanField(required=False, initial=True, label="Incluir")
    source_index = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    codigo = forms.CharField(required=False, max_length=160, label="Código")
    descripcion = forms.CharField(max_length=1000, label="Descripción")
    cantidad = forms.DecimalField(required=False, max_digits=18, decimal_places=4, min_value=0, label="Cantidad")
    unidad = forms.CharField(required=False, max_length=40, label="Unidad")
    precio_unitario = forms.DecimalField(required=False, max_digits=18, decimal_places=4, min_value=0, label="Precio unitario")
    importe = forms.DecimalField(required=False, max_digits=18, decimal_places=2, min_value=0, label="Importe")
    alcance = forms.ChoiceField(choices=ConceptoOferta.Alcance.choices, label="Alcance")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap_fields(self)


class BaseBudgetV3ItemFormSet(forms.BaseFormSet):
    def __init__(self, *args, expected_count=None, **kwargs):
        self.expected_count = expected_count
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        indices = [form.cleaned_data.get("source_index") for form in self.forms]
        if self.expected_count is not None:
            expected = set(range(self.expected_count))
            if len(indices) != self.expected_count or set(indices) != expected:
                raise forms.ValidationError(
                    "La preview ha cambiado. Recargue el documento antes de confirmar."
                )
        if not any(form.cleaned_data.get("selected") for form in self.forms):
            raise forms.ValidationError("Debe confirmar al menos una partida.")


BudgetV3ItemFormSet = forms.formset_factory(
    BudgetV3ItemForm,
    formset=BaseBudgetV3ItemFormSet,
    extra=0,
    max_num=200,
    validate_max=True,
)


# COMPARATIVAS_V2C_EDIT_CONFIRMED_CONCEPTS_R1


class ConceptoConfirmedEditForm(
    forms.Form
):
    concept_id = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
    )

    titulo = forms.CharField(
        max_length=500,
        label="Concepto",
    )

    descripcion = forms.CharField(
        required=False,
        label="Descripción",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
            }
        ),
    )

    cantidad = forms.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=4,
        label="Cantidad",
    )

    unidad = forms.CharField(
        required=False,
        max_length=40,
        label="Unidad",
    )

    precio_unitario = forms.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=4,
        label="Precio unitario",
    )

    importe = forms.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=2,
        label="Importe",
    )

    alcance = forms.ChoiceField(
        choices=(
            ConceptoOferta
            .Alcance
            .choices
        ),
        label="Alcance",
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        _bootstrap_fields(
            self
        )


class BaseConceptoConfirmedEditFormSet(
    forms.BaseFormSet
):
    def __init__(
        self,
        *args,
        expected_ids=None,
        **kwargs,
    ):
        self.expected_ids = {
            int(value)
            for value
            in (
                expected_ids
                or []
            )
        }

        super().__init__(
            *args,
            **kwargs,
        )

    def clean(self):
        super().clean()

        if any(
            self.errors
        ):
            return

        received = []

        for form in self.forms:
            received.append(
                form.cleaned_data[
                    "concept_id"
                ]
            )

        if (
            len(received)
            != len(
                self.expected_ids
            )
            or len(
                set(received)
            )
            != len(received)
            or set(received)
            != self.expected_ids
        ):
            raise forms.ValidationError(
                (
                    "El conjunto de conceptos "
                    "ha cambiado o no es válido. "
                    "Recarga la pantalla."
                )
            )


ConceptoConfirmedEditFormSet = (
    forms.formset_factory(
        ConceptoConfirmedEditForm,
        formset=(
            BaseConceptoConfirmedEditFormSet
        ),
        extra=0,
        max_num=200,
        validate_max=True,
    )
)
