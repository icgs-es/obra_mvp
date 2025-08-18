from django import forms
from django.forms import DateInput, NumberInput, Select
from .models import Obra, Capitulo, Tarea, Planificacion, RecursoPersonal, RecursoMaterial

class PlanificacionManualForm(forms.Form):
    obra=forms.ModelChoiceField(queryset=Obra.objects.all(),required=True,label='Obra')
    capitulo=forms.ModelChoiceField(queryset=Capitulo.objects.none(),required=True,label='Capítulo')
    fecha=forms.DateField(widget=DateInput(attrs={'type':'date'}),required=True,label='Fecha')
    tipo=forms.ChoiceField(choices=Planificacion.TIPO,widget=Select,required=True,label='Tipo')
    recurso_personal=forms.ModelChoiceField(queryset=RecursoPersonal.objects.all(),required=False,label='Persona')
    recurso_material=forms.ModelChoiceField(queryset=RecursoMaterial.objects.all(),required=False,label='Material')
    horas_plan=forms.DecimalField(required=False,min_value=0,decimal_places=2,max_digits=10,widget=NumberInput(attrs={'step':'0.25'}),label='Horas plan')
    cantidad_plan=forms.DecimalField(required=False,min_value=0,decimal_places=3,max_digits=12,widget=NumberInput(attrs={'step':'0.001'}),label='Cantidad plan')
    importe_plan=forms.DecimalField(required=False,min_value=0,decimal_places=2,max_digits=12,widget=NumberInput(attrs={'step':'0.01'}),label='Importe plan')
    def __init__(self,*a,**kw):
        obra_id=kw.pop('obra_id',None); super().__init__(*a,**kw)
        from .models import Capitulo
        self.fields['capitulo'].queryset=Capitulo.objects.all() if not obra_id else Capitulo.objects.filter(obra_id=obra_id)
    def save(self):
        cap=self.cleaned_data['capitulo']; from .models import Tarea, Planificacion
        tarea,_=Tarea.objects.get_or_create(capitulo=cap,nombre='Previsión manual')
        return Planificacion.objects.create(
            tarea=tarea,fecha=self.cleaned_data['fecha'],tipo=self.cleaned_data['tipo'],
            recurso_personal=self.cleaned_data.get('recurso_personal'),
            recurso_material=self.cleaned_data.get('recurso_material'),
            horas_plan=self.cleaned_data.get('horas_plan') or 0,
            cantidad_plan=self.cleaned_data.get('cantidad_plan') or 0,
            importe_plan=self.cleaned_data.get('importe_plan') or 0)
