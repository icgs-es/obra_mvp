from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q

from .attachment_validation import validate_attachment_batch


User = get_user_model()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(item, initial) for item in files]


class PreguntaIAForm(forms.Form):
    pregunta = forms.CharField(
        label="Pregunta",
        max_length=8000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": (
                    "Pregunta, redacta, analiza o desarrolla "
                    "una idea con INTASA IA..."
                ),
                "autocomplete": "off",
            }
        ),
    )
    adjuntos = MultipleFileField(
        label="Adjuntar archivos",
        required=False,
        widget=MultipleFileInput(
            attrs={
                "accept": ".pdf,.jpg,.jpeg,.png,.webp,.docx,.xlsx,.xls,.csv,.txt",
                "class": "visually-hidden",
                "data-ia-attachments": "",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        question = str(cleaned.get("pregunta") or "").strip()
        uploads = cleaned.get("adjuntos") or []
        if not question and not uploads:
            raise forms.ValidationError("Escribe una pregunta o adjunta al menos un archivo.")
        if uploads:
            try:
                cleaned["validated_attachments"] = validate_attachment_batch(uploads)
            except forms.ValidationError as exc:
                self.add_error("adjuntos", exc)
        cleaned["pregunta"] = question
        return cleaned


class CompartirConversacionForm(forms.Form):
    usuario = forms.ModelChoiceField(
        label="Compartir con",
        queryset=User.objects.none(),
        empty_label="Selecciona un usuario",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    def __init__(
        self,
        *,
        owner,
        conversation,
        **kwargs,
    ):
        super().__init__(**kwargs)

        permission = Permission.objects.filter(
            content_type__app_label="intasa_ia",
            codename="use_intasa_ia",
        ).first()

        queryset = (
            User.objects
            .filter(is_active=True)
            .exclude(pk=owner.pk)
        )

        if permission is not None:
            queryset = queryset.filter(
                Q(is_superuser=True)
                | Q(user_permissions=permission)
                | Q(groups__permissions=permission)
            )

        if not owner.is_superuser:
            team_ids = list(
                owner.teams.values_list(
                    "id",
                    flat=True,
                )
            )

            queryset = queryset.filter(
                Q(is_superuser=True)
                | Q(teams__id__in=team_ids)
            )

        shared_user_ids = (
            conversation.accesos_compartidos
            .values_list("user_id", flat=True)
        )

        queryset = (
            queryset
            .exclude(pk__in=shared_user_ids)
            .distinct()
            .order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

        self.fields["usuario"].queryset = queryset

        self.fields["usuario"].label_from_instance = (
            lambda user: (
                user.get_full_name().strip()
                or user.username
            )
        )
