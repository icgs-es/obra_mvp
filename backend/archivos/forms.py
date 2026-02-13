from django import forms
from .models import Carpeta

class CarpetaForm(forms.ModelForm):
    class Meta:
        model = Carpeta
        fields = ["nombre", "visibilidad", "departamento"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre de la carpeta",
                }
            ),
            "visibilidad": forms.Select(
                attrs={"class": "form-select"}
            ),
            # 👇 AQUÍ cambiamos a Select, nada de placeholder de texto
            "departamento": forms.Select(
                attrs={"class": "form-select"}
            ),
        }

class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class SubirArchivoForm(forms.Form):
    fichero = forms.FileField(
        required=True,
        widget=MultiFileInput(attrs={
            "class": "form-control",
            "multiple": True,
        })
    )
    descripcion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 6,
            "placeholder": "Descripción (opcional)...",
        })
    )