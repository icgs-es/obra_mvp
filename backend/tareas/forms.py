from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Tarea

User = get_user_model()

VISIBILIDAD_CHOICES = (
    ("privada", "Privada"),
    ("depto", "Departamento"),
    ("global", "Global"),
)

class TareaForm(forms.ModelForm):
    vencimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Fecha límite (opcional).",
    )

    asignados = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        required=False,
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "size": "6",
        }),
        help_text="Personas asignadas a la tarea (incluye automáticamente al creador)",
    )

    # Forzamos visibilidad como ChoiceField (modelo usa CharField sin choices)
    visibilidad = forms.ChoiceField(
        choices=VISIBILIDAD_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="privada · depto · global",
    )

    class Meta:
        model = Tarea
        fields = [
            "titulo",
            "descripcion",
            "estado",
            "prioridad",
            "vencimiento",
            "etiquetas",
            "visibilidad",
            "asignados",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nueva tarea…", "autofocus": True}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Detalles / pasos / notas…"}),
            "estado": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "prioridad": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "etiquetas": forms.TextInput(attrs={"class": "form-control", "placeholder": "p.ej. bug,frontend,cliente"}),
            # visibilidad se redefine como ChoiceField arriba
        }
        help_texts = {
            "visibilidad": "privada · depto · global",
        }

    def clean_etiquetas(self):
        val = (self.cleaned_data.get("etiquetas") or "").strip()
        if not val:
            return ""
        # normaliza: sin espacios alrededor y única
        tags = [t.strip() for t in val.split(",") if t.strip()]
        return ",".join(dict.fromkeys(tags))  # quita duplicados preservando orden
