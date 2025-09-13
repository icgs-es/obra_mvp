
from django.urls import path
from django.http import HttpResponse

# Intenta importar vistas existentes (planificación, gantt, tesorería, partes)
try:
    from . import ui_views
except Exception:
    ui_views = None
try:
    from . import ui_views_extra
except Exception:
    ui_views_extra = None

# Cargas perezosas para que nunca tumben el servidor
def tabs_home_lazy(request):
    try:
        from .ui_views_tabs import tabs_home
        return tabs_home(request)
    except Exception as e:
        return HttpResponse(f"Tabs home error: {e}", status=500, content_type="text/plain")

def tab_obras_lazy(request):
    try:
        from .ui_views_tabs import tab_obras
        return tab_obras(request)
    except Exception as e:
        return HttpResponse(f"Tab obras error: {e}", status=500, content_type="text/plain")

def tab_subobras_lazy(request):
    try:
        from .ui_views_tabs import tab_subobras
        return subobras(request)
    except Exception as e:
        return HttpResponse(f"Tab subobras error: {e}", status=500, content_type="text/plain")

def tab_capitulos_lazy(request):
    try:
        from .ui_views_tabs import tab_capitulos
        return tab_capitulos(request)
    except Exception as e:
        return HttpResponse(f"Tab capitulos error: {e}", status=500, content_type="text/plain")

def tab_partidas_lazy(request):
    try:
        from .ui_views_tabs import tab_partidas
        return tab_partidas(request)
    except Exception as e:
        return HttpResponse(f"Tab partidas error: {e}", status=500, content_type="text/plain")

urlpatterns = []

# Rutas que ya tenías
if ui_views and hasattr(ui_views, "manual_planificacion"):
    urlpatterns.append(path("planificacion/", ui_views.manual_planificacion, name="manual_planificacion"))
if ui_views_extra:
    if hasattr(ui_views_extra, "gantt"):
        urlpatterns.append(path("gantt/", ui_views_extra.gantt, name="gantt"))
    if hasattr(ui_views_extra, "tesoreria"):
        urlpatterns.append(path("tesoreria/", ui_views_extra.tesoreria, name="tesoreria"))
    if hasattr(ui_views_extra, "parte_alta"):
        urlpatterns.append(path("partes/alta/", ui_views_extra.parte_alta, name="parte_alta"))

# Rutas nuevas de pestañas
urlpatterns += [
    path("tabs/", tabs_home_lazy, name="tabs_home"),
    path("tabs/obras/", tab_obras_lazy, name="tab_obras"),
    path("tabs/subobras/", tab_subobras_lazy, name="tab_subobras"),
    path("tabs/capitulos/", tab_capitulos_lazy, name="tab_capitulos"),
    path("tabs/partidas/", tab_partidas_lazy, name="tab_partidas"),
]
