from django import forms
from django.contrib.auth import get_user_model
from .models import Ausencia, Fichaje

class ISODateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        # Forzamos el formato ISO que entiende <input type="date">
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)

class AusenciaForm(forms.ModelForm):
    class Meta:
        model = Ausencia
        fields = [
            "empleado",
            "tipo",
            "fecha_inicio",
            "fecha_fin",
            "horas",
            "motivo",
            "estado",
        ]
        widgets = {
            "empleado": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": ISODateInput(attrs={"class": "form-control"}),
            "fecha_fin": ISODateInput(attrs={"class": "form-control"}),
            "horas": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.25",
                }
            ),
            "motivo": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
            "estado": forms.Select(attrs={"class": "form-select"}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Desactivamos localización en los campos de fecha
        for name in ["fecha_inicio", "fecha_fin"]:
            self.fields[name].localize = False