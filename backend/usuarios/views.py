from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.views.generic import ListView, CreateView, UpdateView, View
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone

User = get_user_model()

class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return u.is_superuser or u.groups.filter(name="Administrador").exists()

class UsuarioListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    template_name = "usuarios/list.html"
    model = User
    paginate_by = 50
    def get_queryset(self):
        qs = super().get_queryset().order_by("-is_active","username")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(email__icontains=q)
        return qs

class UsuarioCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    template_name = "usuarios/form.html"
    model = User
    fields = ["username","email"]  # añade aquí 'full_name' u otros si tu modelo los tiene
    success_url = reverse_lazy("usuarios:list")

    def form_valid(self, form):
        resp = super().form_valid(form)
        pwd = self.request.POST.get("initial_password","")
        if pwd:
            self.object.set_password(pwd); self.object.save()
        roles = self.request.POST.getlist("roles")
        groups = Group.objects.filter(name__in=roles)
        self.object.groups.set(groups)
        return resp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["all_roles"] = Group.objects.all().order_by("name")
        return ctx

class UsuarioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    template_name = "usuarios/form.html"
    model = User
    fields = ["username","email"]
    success_url = reverse_lazy("usuarios:list")

    def form_valid(self, form):
        resp = super().form_valid(form)
        pwd = self.request.POST.get("initial_password","")
        if pwd:
            self.object.set_password(pwd); self.object.save()
        roles = self.request.POST.getlist("roles")
        groups = Group.objects.filter(name__in=roles)
        self.object.groups.set(groups)
        return resp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["all_roles"] = Group.objects.all().order_by("name")
        ctx["selected_roles"] = self.object.groups.values_list("name", flat=True)
        return ctx

class UsuarioDeactivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_active = False
        if hasattr(user, "fecha_baja"):
            user.fecha_baja = timezone.now()
        user.save()
        return redirect("usuarios:list")
