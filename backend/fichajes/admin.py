from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Fichaje, Ausencia, TerminalFichaje

User = get_user_model()


@admin.register(Fichaje)
class FichajeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "team",
        "tipo",
        "timestamp",
        "origen",
        "ip",
        "lat",
        "lng",
        "corregido",
    )
    list_filter = (
        "team",
        "tipo",
        "origen",
        "corregido",
        "timestamp",
    )
    search_fields = (
        "team__name",
        "user__username",
        "user__first_name",
        "user__last_name",
        "ip",
    )
    readonly_fields = (
        "timestamp",
        "created_at",
        "updated_at",
        "ip",
        "user_agent",
    )


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ("empleado", "tipo", "fecha_inicio", "fecha_fin", "estado")
    list_filter = ("tipo", "estado", "fecha_inicio")
    search_fields = ("empleado__username", "empleado__first_name", "empleado__last_name")


@admin.register(TerminalFichaje)
class TerminalFichajeAdmin(admin.ModelAdmin):
    list_display = ("user", "pin", "activo", "descripcion")
    list_filter = ("activo",)
    search_fields = (
        "pin",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("user",)


class TerminalFichajeInline(admin.StackedInline):
    model = TerminalFichaje
    can_delete = True
    extra = 0


class UserAdmin(BaseUserAdmin):
    inlines = [TerminalFichajeInline]


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, UserAdmin)
