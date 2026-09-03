from django import forms
from .models import ActivoCore


class ActivoForm(forms.ModelForm):
    class Meta:
        model = ActivoCore
        fields = [
            "codigo_externo",
            "nombre",
            "tipo_activo",
            "estado_operativo",
            "situacion_activo",
            "origen_sistema",
        ]