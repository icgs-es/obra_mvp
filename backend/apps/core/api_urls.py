from rest_framework.routers import DefaultRouter
from .api_views import (
    ObraViewSet, CapituloViewSet, TareaViewSet, PlanificacionViewSet,
    RecursoPersonalViewSet, RecursoMaterialViewSet,
    ParteTrabajoViewSet, ProveedorViewSet, FacturaProveedorViewSet, VencimientoViewSet,
    AusenciaViewSet
)

router = DefaultRouter()
router.register(r"obras", ObraViewSet)
router.register(r"capitulos", CapituloViewSet)
router.register(r"tareas", TareaViewSet)
router.register(r"planificaciones", PlanificacionViewSet)
router.register(r"recursos-personal", RecursoPersonalViewSet)
router.register(r"recursos-material", RecursoMaterialViewSet)
router.register(r"partes", ParteTrabajoViewSet)
router.register(r"proveedores", ProveedorViewSet)
router.register(r"facturas", FacturaProveedorViewSet)
router.register(r"vencimientos", VencimientoViewSet)
router.register(r"ausencias", AusenciaViewSet)

urlpatterns = router.urls
