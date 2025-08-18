from datetime import date, datetime
from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from .models import Obra, Capitulo, Planificacion
from .forms import PlanificacionManualForm

def _parse_date(s, default=None):
    try: return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception: return default

@require_http_methods(['GET','POST'])
def manual_planificacion(request):
    obra_id=request.GET.get('obra') or None
    capitulo_id=request.GET.get('capitulo') or None
    periodo=request.GET.get('periodo') or 'mes'
    ini=_parse_date(request.GET.get('ini'), date.today().replace(day=1))
    fin=_parse_date(request.GET.get('fin'), date.today())
    form=PlanificacionManualForm(request.POST or None, obra_id=obra_id)
    if request.method=='POST' and form.is_valid():
        form.save(); return redirect(request.get_full_path())
    qs=Planificacion.objects.select_related('tarea__capitulo__obra').filter(fecha__range=(ini,fin))
    if obra_id: qs=qs.filter(tarea__capitulo__obra_id=obra_id)
    if capitulo_id: qs=qs.filter(tarea__capitulo_id=capitulo_id)
    key=TruncWeek('fecha') if periodo=='semana' else TruncMonth('fecha')
    rows=(qs.annotate(periodo=key).values('periodo').annotate(importe=Sum('importe_plan'),horas=Sum('horas_plan'),cantidad=Sum('cantidad_plan')).order_by('periodo'))
    return render(request, 'core/manual_planificacion.html', {'form':form,'obras':Obra.objects.all().order_by('codigo'),'capitulos':Capitulo.objects.all().order_by('obra','orden','codigo'),'obra_sel':int(obra_id) if obra_id else None,'capitulo_sel':int(capitulo_id) if capitulo_id else None,'ini':ini,'fin':fin,'periodo':periodo,'rows':rows})
