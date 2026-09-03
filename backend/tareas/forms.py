from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from usuarios.models import Team

from .access import assignee_queryset_for_task
from .models import Tarea


User = get_user_model()


VISIBILIDAD_CHOICES = (
    ("privada", "Privada"),
    ("depto", "Departamento"),
    ("global", "Global"),
)


class TareaForm(forms.ModelForm):
    team = forms.ModelChoiceField(
        label="Empresa",
        queryset=Team.objects.none(),
        required=False,
        empty_label="Selecciona una empresa",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    vencimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        help_text="Fecha límite (opcional).",
    )

    inicio_programado = forms.DateTimeField(
        required=False,
        label="Inicio programado",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
        help_text="Opcional. Si se indica, la tarea aparecerá con hora en Agenda.",
    )

    fin_programado = forms.DateTimeField(
        required=False,
        label="Fin programado",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
        help_text="Opcional; requiere un inicio programado.",
    )

    asignados = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select",
                "size": "6",
            }
        ),
        help_text=(
            "Personas asignadas a la tarea. "
            "Solo se muestran usuarios de la empresa."
        ),
    )

    visibilidad = forms.ChoiceField(
        choices=VISIBILIDAD_CHOICES,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
        help_text=(
            "Privada: creador/asignados. "
            "Departamento o global: empresa."
        ),
    )

    class Meta:
        model = Tarea

        fields = [
            "team",
            "titulo",
            "descripcion",
            "estado",
            "prioridad",
            "vencimiento",
            "inicio_programado",
            "fin_programado",
            "etiquetas",
            "visibilidad",
            "asignados",
        ]

        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nueva tarea…",
                    "autofocus": True,
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Detalles / pasos / notas…"
                    ),
                }
            ),
            "estado": forms.RadioSelect(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "prioridad": forms.RadioSelect(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "etiquetas": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "p.ej. bug,frontend,cliente"
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        team=None,
        **kwargs,
    ):
        instance = kwargs.get("instance")

        allowed_teams = (
            Team.objects.all()
            if user is not None and user.is_superuser
            else Team.objects.filter(members=user)
        ).order_by("name", "pk").distinct()

        super().__init__(
            *args,
            **kwargs,
        )

        self.user = user
        self.team = team
        self.fields["team"].queryset = allowed_teams

        selected_team = team
        if self.is_bound:
            raw_team = self.data.get("team")
            if str(raw_team or "").isdigit():
                selected_team = allowed_teams.filter(pk=int(raw_team)).first()
        elif instance is not None and instance.team_id:
            selected_team = instance.team
            self.fields["team"].initial = instance.team_id
        elif team is not None:
            self.fields["team"].initial = team.pk

        self.fields[
            "asignados"
        ].queryset = assignee_queryset_for_task(
            user=user,
            team=selected_team,
            instance=self.instance,
        )

        datetime_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
        ]
        for field_name in ("inicio_programado", "fin_programado"):
            self.fields[field_name].input_formats = datetime_formats
            value = getattr(instance, field_name, None) if instance else None
            if value:
                self.fields[field_name].initial = timezone.localtime(value).strftime(
                    "%Y-%m-%dT%H:%M"
                )

    def clean_team(self):
        selected = self.cleaned_data.get("team")
        if selected is None:
            if not self.instance.pk:
                raise forms.ValidationError(
                    "Selecciona una empresa concreta antes de crear la tarea.",
                    code="required_team",
                )
            return None
        if (
            not self.user.is_superuser
            and not self.user.teams.filter(pk=selected.pk).exists()
        ):
            raise forms.ValidationError(
                "No tienes acceso a la empresa seleccionada.",
                code="invalid_team",
            )
        if (
            self.instance.pk
            and self.instance.team_id
            and selected.pk != self.instance.team_id
        ):
            raise forms.ValidationError(
                "No se puede cambiar la empresa de una tarea existente.",
                code="team_change_forbidden",
            )
        return selected

    def clean_etiquetas(self):
        value = (
            self.cleaned_data.get(
                "etiquetas"
            )
            or ""
        ).strip()

        if not value:
            return ""

        tags = [
            item.strip()
            for item
            in value.split(",")
            if item.strip()
        ]

        return ",".join(
            dict.fromkeys(tags)
        )

    def clean_asignados(self):
        assigned = self.cleaned_data.get(
            "asignados"
        )

        if assigned is None:
            return assigned

        selected_team = self.cleaned_data.get("team")
        if selected_team is not None:
            invalid = assigned.exclude(
                teams=selected_team
            )

            if invalid.exists():
                raise forms.ValidationError(
                    "Hay usuarios que no pertenecen "
                    "a la empresa seleccionada.",
                    code="cross_team_assignee",
                )

        return assigned

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("inicio_programado")
        end = cleaned.get("fin_programado")
        if end is not None and start is None:
            self.add_error(
                "fin_programado",
                forms.ValidationError(
                    "Indica un inicio programado antes del fin.",
                    code="end_without_start",
                ),
            )
        elif start is not None and end is not None and end < start:
            self.add_error(
                "fin_programado",
                forms.ValidationError(
                    "El fin programado no puede ser anterior al inicio.",
                    code="end_before_start",
                ),
            )
        return cleaned
