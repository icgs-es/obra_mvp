from rest_framework import viewsets, filters
from rest_framework.pagination import PageNumberPagination

from .models import (
    Obra, Capitulo, Tarea, Planificacion,
    RecursoPersonal, RecursoMaterial,
    ParteTrabajo, Proveedor, FacturaProveedor, Vencimiento, Ausencia
)
from .serializers import (
    ObraSerializer, CapituloSerializer, TareaSerializer, PlanificacionSerializer,
    RecursoPersonalSerializer, RecursoMaterialSerializer,
    ParteTrabajoSerializer, ProveedorSerializer, FacturaProveedorSerializer, VencimientoSerializer,
    AusenciaSerializer
)

class DefaultPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500

class BaseViewSet(viewsets.ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id"]
    ordering_fields = ["id"]
    ordering = ["id"]

class ObraViewSet(BaseViewSet):
    queryset = Obra.objects.all()
    serializer_class = ObraSerializer
    search_fields = ["codigo", "nombre", "cliente"]
    ordering_fields = ["codigo", "nombre"]

class CapituloViewSet(BaseViewSet):
    queryset = Capitulo.objects.select_related("obra").all()
    serializer_class = CapituloSerializer
    search_fields = ["codigo", "nombre", "obra__codigo"]
    ordering_fields = ["obra", "orden", "codigo"]

class TareaViewSet(BaseViewSet):
    queryset = Tarea.objects.select_related("capitulo__obra").all()
    serializer_class = TareaSerializer
    search_fields = ["nombre", "capitulo__codigo", "capitulo__obra__codigo"]
    ordering_fields = ["fecha_inicio_plan", "fecha_fin_plan"]

class RecursoPersonalViewSet(BaseViewSet):
    queryset = RecursoPersonal.objects.all()
    serializer_class = RecursoPersonalSerializer
    search_fields = ["nombre", "especialidad"]
    ordering_fields = ["nombre"]

class RecursoMaterialViewSet(BaseViewSet):
    queryset = RecursoMaterial.objects.all()
    serializer_class = RecursoMaterialSerializer
    search_fields = ["referencia", "nombre"]
    ordering_fields = ["referencia", "nombre"]

class PlanificacionViewSet(BaseViewSet):
    queryset = Planificacion.objects.select_related(
        "tarea__capitulo__obra", "recurso_personal", "recurso_material"
    ).all()
    serializer_class = PlanificacionSerializer
    search_fields = ["tarea__capitulo__obra__codigo", "tarea__capitulo__codigo", "tarea__nombre"]
    ordering_fields = ["fecha", "tipo", "importe_plan"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        obra = params.get("obra")
        capitulo = params.get("capitulo")
        fini = params.get("ini")
        ffin = params.get("fin")
        tipo = params.get("tipo")

        if obra:
            qs = qs.filter(tarea__capitulo__obra_id=obra)
        if capitulo:
            qs = qs.filter(tarea__capitulo_id=capitulo)
        if fini and ffin:
            qs = qs.filter(fecha__range=[fini, ffin])
        if tipo in ("PERSONAL", "MATERIAL"):
            qs = qs.filter(tipo=tipo)
        return qs

class ParteTrabajoViewSet(BaseViewSet):
    queryset = ParteTrabajo.objects.select_related("obra", "capitulo", "recurso", "tarea").all()
    serializer_class = ParteTrabajoSerializer
    search_fields = ["obra__codigo", "capitulo__codigo", "recurso__nombre"]
    ordering_fields = ["fecha", "horas"]

class ProveedorViewSet(BaseViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer
    search_fields = ["nombre", "nif"]
    ordering_fields = ["nombre"]

class FacturaProveedorViewSet(BaseViewSet):
    queryset = FacturaProveedor.objects.select_related("proveedor", "obra", "capitulo").all()
    serializer_class = FacturaProveedorSerializer
    search_fields = ["numero", "proveedor__nombre", "obra__codigo"]
    ordering_fields = ["fecha", "total"]

class VencimientoViewSet(BaseViewSet):
    queryset = Vencimiento.objects.select_related("factura", "factura__proveedor").all()
    serializer_class = VencimientoSerializer
    search_fields = ["factura__numero", "factura__proveedor__nombre"]
    ordering_fields = ["fecha_venc", "importe"]

class AusenciaViewSet(BaseViewSet):
    queryset = Ausencia.objects.select_related("recurso").all()
    serializer_class = AusenciaSerializer
    search_fields = ["recurso__nombre", "tipo"]
    ordering_fields = ["fecha_inicio", "fecha_fin"]
