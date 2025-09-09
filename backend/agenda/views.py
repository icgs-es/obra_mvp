from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.utils import timezone
from .models import Evento

class AgendaView(LoginRequiredMixin, TemplateView):
    template_name = "agenda/agenda.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        start = timezone.make_aware(timezone.datetime.combine(hoy, timezone.datetime.min.time()))
        end = start + timezone.timedelta(days=7)
        ctx["eventos"] = Evento.objects.filter(inicio__gte=start, inicio__lt=end).order_by("inicio")
        ctx["hoy"] = hoy
        return ctx

class EventoCreateView(LoginRequiredMixin, CreateView):
    template_name = "agenda/form.html"
    model = Evento
    fields = ["titulo","inicio","fin","all_day","ubicacion","notas","recordatorio_min","visibilidad"]
    success_url = reverse_lazy("agenda:home")

class EventoUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "agenda/form.html"
    model = Evento
    fields = ["titulo","inicio","fin","all_day","ubicacion","notas","recordatorio_min","visibilidad"]
    success_url = reverse_lazy("agenda:home")
