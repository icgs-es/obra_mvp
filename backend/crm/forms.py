from django import forms
from .models import Lead


class ImportLeadsForm(forms.Form):
    file = forms.FileField(label="Archivo CSV")


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "fuente",
            "fecha",
            "activo",
            "tipo_activo",
            "precio",
            "dorm",
            "interes",
            "nombre",
            "telefono",
            "email",
            "seatable",
            "inmovilla",
            "contestada",
            "contestada_at",
            "seatable_at",
            "inmovilla_at",
            "visita",
            "visita_at",
            "estado",
            "notas",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "contestada_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "seatable_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "inmovilla_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "visita_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "precio": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        date_fields = {"fecha", "contestada_at", "seatable_at", "inmovilla_at", "visita_at"}
        checkbox_fields = {"seatable", "inmovilla", "contestada", "visita"}
        special_fields = date_fields | {"estado", "notas"} | checkbox_fields
        for name, field in self.fields.items():
            if name in date_fields or name in {"estado", "notas"}:
                continue
            if name in checkbox_fields:
                field.widget.attrs["class"] = "form-check-input"
                continue
            existing_classes = field.widget.attrs.get("class", "")
            classes = f"{existing_classes} form-control".strip()
            field.widget.attrs["class"] = classes
