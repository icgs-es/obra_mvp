from django import forms
from django.forms import DateInput, NumberInput
from .models import ParteTrabajo

class ParteTrabajoForm(forms.ModelForm):
    class Meta:
        model = ParteTrabajo
        fields = ["recurso", "obra", "capitulo", "tarea", "fecha", "horas", "observaciones"]
        widgets = {"fecha": DateInput(attrs={"type":"date"}), "horas": NumberInput(attrs={"step":"0.25"})}
