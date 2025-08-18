from rest_framework import serializers
from .models import (
    Obra, Capitulo, Tarea, Planificacion,
    RecursoPersonal, RecursoMaterial,
    ParteTrabajo, Proveedor, FacturaProveedor, Vencimiento, Ausencia
)

class ObraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Obra
        fields = "__all__"

class CapituloSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capitulo
        fields = "__all__"

class TareaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tarea
        fields = "__all__"

class RecursoPersonalSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecursoPersonal
        fields = "__all__"

class RecursoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecursoMaterial
        fields = "__all__"

class PlanificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Planificacion
        fields = "__all__"

class ParteTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParteTrabajo
        fields = "__all__"

class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = "__all__"

class FacturaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacturaProveedor
        fields = "__all__"

class VencimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vencimiento
        fields = "__all__"

class AusenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ausencia
        fields = "__all__"
