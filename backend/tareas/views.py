from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.utils import timezone
from .models import Tarea

class TareaListView(LoginRequiredMixin, ListView):
    template_name = "tareas/list.html"
    model = Tarea
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by("-creado")
        f = self.request.GET.get("f")
        hoy = timezone.localdate()
        if f == "hoy":
            qs = qs.filter(vencimiento=hoy)
        elif f == "atrasadas":
            qs = qs.filter(vencimiento__lt=hoy, estado__in=["pendiente","en_curso","bloqueada"])
        return qs

class TareaCreateView(LoginRequiredMixin, CreateView):
    template_name = "tareas/form.html"
    model = Tarea
    fields = ["titulo","descripcion","estado","prioridad","vencimiento","etiquetas","visibilidad"]
    success_url = reverse_lazy("tareas:list")

    def form_valid(self, form):
        form.instance.creador = self.request.user
        resp = super().form_valid(form)
        self.object.asignados.add(self.request.user)  # auto-asignar creador
        return resp

class TareaUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "tareas/form.html"
    model = Tarea
    fields = ["titulo","descripcion","estado","prioridad","vencimiento","etiquetas","visibilidad"]
    success_url = reverse_lazy("tareas:list")

class TareaKanbanView(LoginRequiredMixin, TemplateView):
    template_name = "tareas/kanban.html"
