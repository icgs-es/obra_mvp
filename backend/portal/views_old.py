from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.shortcuts import render

@method_decorator(login_required, name='dispatch')
class DashboardView(TemplateView):
    template_name = 'portal/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        # Aquí puedes añadir más datos para el dashboard
        return context

# Vista simple para verificar que /app/ funciona
#@login_required
#def app_home(request):
#    return render(request, 'portal/dashboard.html', {'user': request.user})


@login_required
def dashboard(request):
    """
    Vista mínima para /app/ (Mi jornada).
    Muestra enlaces a Tareas y Agenda y un saludo.
    """
    ctx = {
        "now": timezone.now(),
    }
    return render(request, "portal/index.html", ctx)
