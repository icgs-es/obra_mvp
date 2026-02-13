from django import forms
from django.utils import timezone
from .models import Tarea

class TareaForm(forms.ModelForm):
    vencimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type":"date","class":"form-control"}),
        help_text="Fecha límite (opcional)."
    )

    class Meta:
        model = Tarea
        fields = ["titulo","descripcion","estado","prioridad","vencimiento","etiquetas","visibilidad"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class":"form-control","placeholder":"Nueva tarea…"}),
            "descripcion": forms.Textarea(attrs={"class":"form-control","rows":5,"placeholder":"Detalles / pasos / notas…"}),
            "estado": forms.Select(attrs={"class":"form-select"}),
            "prioridad": forms.Select(attrs={"class":"form-select"}),
            "etiquetas": forms.TextInput(attrs={"class":"form-control","placeholder":"coma,separadas,así"}),
            "visibilidad": forms.Select(attrs={"class":"form-select"}),
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
