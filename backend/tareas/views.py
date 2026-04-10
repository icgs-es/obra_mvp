from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from .models import Tarea
from .forms import TareaForm

class TareaListView(LoginRequiredMixin, ListView):
    template_name = "tareas/list.html"
    model = Tarea
    context_object_name = "tareas"
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
    form_class = TareaForm
    success_url = reverse_lazy("tareas:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "create"
        return ctx

    def form_valid(self, form):
        form.instance.creador = self.request.user
        resp = super().form_valid(form)
        # auto-asignar creador si no está ya
        if not self.object.asignados.filter(pk=self.request.user.pk).exists():
            self.object.asignados.add(self.request.user)
        return resp

    def get_success_url(self):
        if self.request.POST.get("save_add_another"):
            return reverse("tareas:create")
        return super().get_success_url()

class TareaUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "tareas/form.html"
    model = Tarea
    form_class = TareaForm
    success_url = reverse_lazy("tareas:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "edit"
        return ctx

class TareaKanbanView(LoginRequiredMixin, TemplateView):
    template_name = "tareas/kanban.html"
