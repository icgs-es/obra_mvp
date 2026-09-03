from django import forms
from django.contrib.auth import get_user_model

from .models import Empleado, GrupoTrabajo


class EmpleadoForm(forms.ModelForm):
    grupos_trabajo = forms.ModelMultipleChoiceField(
        queryset=GrupoTrabajo.objects.none(),
        required=False,
        label="Grupos de trabajo",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Empleado
        fields = [
            "team",
            "nombre_completo",
            "nif_nie",
            "telefono",
            "email",
            "empresa_empleadora",
            "tipo_relacion",
            "area_principal",
            "puesto",
            "profesion",
            "situacion",
            "fecha_alta",
            "fecha_baja",
            "coste_hora",
            "precio_bruto_hora",
            "coste_bruto_nomina",
            "coste_bruto_ss",
            "sueldo",
            "coeficiente",
            "retencion",
            "es_fichable",
            "es_planificable_obra",
            "activo",
            "user",
            "grupos_trabajo",
        ]

        widgets = {
            "fecha_alta": forms.DateInput(attrs={"type": "date"}),
            "fecha_baja": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)

        user_teams = request_user.teams.all() if request_user else Empleado.objects.none()

        self.fields["team"].queryset = user_teams.order_by("name")
        self.fields["grupos_trabajo"].queryset = (
            GrupoTrabajo.objects
            .filter(team__in=user_teams, activo=True)
            .select_related("team")
            .order_by("team__name", "tipo", "nombre")
        )

        User = get_user_model()
        self.fields["user"].queryset = (
            User.objects
            .filter(teams__in=user_teams)
            .distinct()
            .order_by("username")
        )
        self.fields["user"].required = False

        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput) and not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.setdefault("class", "form-control")

        for name in ["team", "tipo_relacion", "area_principal", "situacion", "user"]:
            self.fields[name].widget.attrs["class"] = "form-select"

        if self.instance and self.instance.pk:
            self.fields["grupos_trabajo"].initial = self.instance.grupos_trabajo.all()

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get("team")
        grupos = cleaned.get("grupos_trabajo")

        if team and grupos:
            invalid = [g for g in grupos if g.team_id != team.id]
            if invalid:
                self.add_error("grupos_trabajo", "Todos los grupos deben pertenecer a la misma empresa del empleado.")

        return cleaned

    def save(self, commit=True):
        empleado = super().save(commit=False)

        if not empleado.origen:
            empleado.origen = "manual"

        if commit:
            empleado.save()
            self.save_m2m()
            empleado.grupos_trabajo.set(self.cleaned_data.get("grupos_trabajo", []))

        return empleado

# ============================================================================
# RRHH_SELECCION_PERSONAL_V1
# ============================================================================

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from archivos.models import Archivo
from usuarios.models import Team

from .models import (
    Candidato,
    Candidatura,
    CandidaturaSeguimiento,
    ProcesoSeleccion,
)


from .services.cv_duplicates import sha256_uploaded_file


def _recruitment_teams_for_user(user):
    if not user:
        return Team.objects.none()
    if user.is_superuser:
        return Team.objects.all()
    return user.teams.all()


class ProcesoSeleccionForm(forms.ModelForm):
    class Meta:
        model = ProcesoSeleccion
        fields = [
            "team",
            "titulo",
            "area",
            "responsable",
            "descripcion",
            "requisitos",
            "estado",
            "fecha_apertura",
            "fecha_cierre",
        ]
        widgets = {
            "fecha_apertura": forms.DateInput(attrs={"type": "date"}),
            "fecha_cierre": forms.DateInput(attrs={"type": "date"}),
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "requisitos": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        teams = _recruitment_teams_for_user(request_user)
        self.fields["team"].queryset = teams.order_by("name")

        User = get_user_model()
        self.fields["responsable"].queryset = (
            User.objects
            .filter(teams__in=teams, is_active=True)
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        self.fields["responsable"].required = False

        for name, field in self.fields.items():
            if name in {"team", "area", "responsable", "estado"}:
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get("team")
        responsable = cleaned.get("responsable")
        fecha_apertura = cleaned.get("fecha_apertura")
        fecha_cierre = cleaned.get("fecha_cierre")

        if (
            team
            and responsable
            and not responsable.is_superuser
            and not responsable.teams.filter(pk=team.pk).exists()
        ):
            self.add_error(
                "responsable",
                "El responsable debe pertenecer a la empresa seleccionada.",
            )

        if fecha_apertura and fecha_cierre and fecha_cierre < fecha_apertura:
            self.add_error(
                "fecha_cierre",
                "La fecha de cierre no puede ser anterior a la apertura.",
            )

        return cleaned


class CandidaturaForm(forms.ModelForm):
    nombre_completo = forms.CharField(max_length=220, label="Nombre completo")
    telefono = forms.CharField(max_length=60, required=False)
    email = forms.EmailField(required=False)
    ciudad = forms.CharField(max_length=120, required=False)
    perfil_profesional = forms.CharField(
        max_length=220,
        required=False,
        label="Perfil profesional",
    )
    linkedin_url = forms.URLField(
        max_length=500,
        required=False,
        label="LinkedIn",
    )
    observaciones_candidato = forms.CharField(
        required=False,
        label="Observaciones generales",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = Candidatura
        fields = [
            "proceso",
            "responsable",
            "origen",
            "fecha_solicitud",
            "estado",
            "puntuacion",
            "fecha_proximo_contacto",
            "fecha_entrevista",
            "observaciones_revision",
            "observaciones_entrevista",
            "cv_archivo",
            "cv_fichero",
        ]
        widgets = {
            "fecha_solicitud": forms.DateInput(attrs={"type": "date"}),
            "fecha_proximo_contacto": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "fecha_entrevista": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "observaciones_revision": forms.Textarea(attrs={"rows": 4}),
            "observaciones_entrevista": forms.Textarea(attrs={"rows": 4}),
            "cv_fichero": forms.ClearableFileInput(
                attrs={"accept": "application/pdf,.pdf"},
            ),
        }

    def __init__(
        self,
        *args,
        request_user=None,
        candidate_instance=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.candidate_instance = candidate_instance

        # RRHH_CANDIDATURA_DATE_WIDGETS_V1
        date_field = self.fields.get("fecha_solicitud")
        if date_field is not None:
            date_field.widget.format = "%Y-%m-%d"
            date_field.widget.attrs["type"] = "date"
            date_field.input_formats = ["%Y-%m-%d"]

        for field_name in (
            "fecha_proximo_contacto",
            "fecha_entrevista",
        ):
            datetime_field = self.fields.get(field_name)
            if datetime_field is None:
                continue
            datetime_field.widget.format = (
                "%Y-%m-%dT%H:%M"
            )
            datetime_field.widget.attrs["type"] = "datetime-local"
            datetime_field.input_formats = [
                "%Y-%m-%dT%H:%M",
            ]
        teams = _recruitment_teams_for_user(request_user)

        self.fields["proceso"].queryset = (
            ProcesoSeleccion.objects
            .filter(team__in=teams)
            .select_related("team")
            .order_by("-fecha_apertura", "team__name", "titulo")
        )

        User = get_user_model()
        self.fields["responsable"].queryset = (
            User.objects
            .filter(teams__in=teams, is_active=True)
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        self.fields["responsable"].required = False

        archivo_qs = (
            Archivo.objects
            .select_related("team", "carpeta")
            .filter(Q(team__in=teams) | Q(team__isnull=True))
            .filter(
                Q(mime_type="application/pdf")
                | Q(nombre_original__iendswith=".pdf")
                | Q(nombre_logico__iendswith=".pdf")
            )
            .order_by("-created_at")
        )

        if request_user and not request_user.is_superuser:
            allowed_ids = [
                archivo.pk
                for archivo in archivo_qs
                if archivo.carpeta.puede_ver(request_user)
            ]
            archivo_qs = archivo_qs.filter(pk__in=allowed_ids)

        self.fields["cv_archivo"].queryset = archivo_qs
        self.fields["cv_archivo"].required = False
        self.fields["cv_archivo"].label = "Vincular CV existente en Archivos"
        self.fields["cv_fichero"].required = False
        self.fields["cv_fichero"].label = "O subir CV nuevo (PDF)"

        self.fields["fecha_proximo_contacto"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]
        self.fields["fecha_entrevista"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        if self.instance and self.instance.pk:
            candidato = self.instance.candidato
            self.fields["nombre_completo"].initial = candidato.nombre_completo
            self.fields["telefono"].initial = candidato.telefono
            self.fields["email"].initial = candidato.email
            self.fields["ciudad"].initial = candidato.ciudad
            self.fields["perfil_profesional"].initial = candidato.perfil_profesional
            self.fields["linkedin_url"].initial = candidato.linkedin_url
            self.fields["observaciones_candidato"].initial = candidato.observaciones

            for date_name in ("fecha_proximo_contacto", "fecha_entrevista"):
                value = getattr(self.instance, date_name, None)
                if value:
                    self.initial[date_name] = timezone.localtime(
                        value
                    ).strftime("%Y-%m-%dT%H:%M")

        for name, field in self.fields.items():
            if name in {
                "proceso",
                "responsable",
                "origen",
                "estado",
                "puntuacion",
                "cv_archivo",
            }:
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_cv_fichero(self):
        uploaded = self.cleaned_data.get("cv_fichero")
        if not uploaded:
            return uploaded

        name = (uploaded.name or "").lower()
        content_type = (getattr(uploaded, "content_type", "") or "").lower()

        if not name.endswith(".pdf") and content_type != "application/pdf":
            raise ValidationError("El currículo nuevo debe ser un archivo PDF.")

        if uploaded.size > 15 * 1024 * 1024:
            raise ValidationError("El currículo no puede superar 15 MB.")

        uploaded._rrhh_cv_sha256 = sha256_uploaded_file(uploaded)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        proceso = cleaned.get("proceso")
        responsable = cleaned.get("responsable")
        cv_archivo = cleaned.get("cv_archivo")
        cv_fichero = cleaned.get("cv_fichero")
        clear_existing = bool(self.data.get("cv_fichero-clear"))
        existing_file = (
            self.instance.cv_fichero
            if self.instance and self.instance.pk and not clear_existing
            else None
        )

        if cv_archivo and (cv_fichero or existing_file):
            self.add_error(
                "cv_archivo",
                "No se puede vincular un CV y mantener/subir otro simultáneamente.",
            )

        if (
            proceso
            and responsable
            and not responsable.is_superuser
            and not responsable.teams.filter(pk=proceso.team_id).exists()
        ):
            self.add_error(
                "responsable",
                "El responsable no pertenece a la empresa del proceso.",
            )

        if (
            proceso
            and cv_archivo
            and cv_archivo.team_id
            and cv_archivo.team_id != proceso.team_id
        ):
            self.add_error(
                "cv_archivo",
                "El archivo pertenece a otra empresa.",
            )

        if proceso and cv_fichero:
            cv_sha256 = getattr(
                cv_fichero,
                "_rrhh_cv_sha256",
                "",
            )
            if cv_sha256:
                duplicate_qs = Candidatura.objects.filter(
                    proceso=proceso,
                    cv_sha256=cv_sha256,
                )
                if self.instance and self.instance.pk:
                    duplicate_qs = duplicate_qs.exclude(
                        pk=self.instance.pk
                    )
                if duplicate_qs.exists():
                    self.add_error(
                        "cv_fichero",
                        "Este PDF ya está asociado a otra "
                        "candidatura del mismo proceso.",
                    )

        return cleaned

    def save(self, commit=True):
        if not commit:
            raise ValueError("CandidaturaForm requiere commit=True.")

        candidatura = super().save(commit=False)
        proceso = self.cleaned_data["proceso"]

        if candidatura.pk:
            candidato = candidatura.candidato
        elif self.candidate_instance is not None:
            candidato = self.candidate_instance
        else:
            candidato = Candidato(
                team=proceso.team,
                creado_por=self.request_user,
            )

        candidato.team = proceso.team
        candidato.nombre_completo = self.cleaned_data["nombre_completo"]
        candidato.telefono = self.cleaned_data.get("telefono", "")
        candidato.email = self.cleaned_data.get("email", "")
        candidato.ciudad = self.cleaned_data.get("ciudad", "")
        candidato.perfil_profesional = self.cleaned_data.get(
            "perfil_profesional",
            "",
        )
        candidato.linkedin_url = self.cleaned_data.get("linkedin_url", "")
        candidato.observaciones = self.cleaned_data.get(
            "observaciones_candidato",
            "",
        )
        candidato.full_clean()
        candidato.save()

        candidatura.candidato = candidato
        # RRHH_CV_OCR_V1 · responsable heredado del proceso.
        if not candidatura.responsable_id:
            candidatura.responsable = proceso.responsable
        candidatura.modificado_por = self.request_user
        if not candidatura.pk:
            candidatura.creado_por = self.request_user

        uploaded = self.cleaned_data.get("cv_fichero")
        if uploaded:
            candidatura.cv_nombre_original = uploaded.name
            candidatura.cv_sha256 = getattr(
                uploaded,
                "_rrhh_cv_sha256",
                "",
            )
        elif self.data.get("cv_fichero-clear"):
            candidatura.cv_nombre_original = ""
            candidatura.cv_sha256 = ""

        candidatura.full_clean()
        candidatura.save()
        self.save_m2m()
        return candidatura


class CandidaturaSeguimientoForm(forms.ModelForm):
    class Meta:
        model = CandidaturaSeguimiento
        fields = ["tipo", "fecha", "completado", "notas", "resultado"]
        widgets = {
            "fecha": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "notas": forms.Textarea(attrs={"rows": 3}),
            "resultado": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.initial.setdefault(
            "fecha",
            timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        )
        self.fields["tipo"].widget.attrs["class"] = "form-select"
        self.fields["fecha"].widget.attrs["class"] = "form-control"
        self.fields["notas"].widget.attrs["class"] = "form-control"
        self.fields["resultado"].widget.attrs["class"] = "form-control"
        self.fields["completado"].widget.attrs["class"] = "form-check-input"
