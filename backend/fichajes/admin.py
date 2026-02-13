from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Fichaje, Ausencia, TerminalFichaje

User = get_user_model()

@admin.register(Fichaje)
class FichajeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tipo",
        "timestamp",
        "origen",     # 👈 aquí
        "ip",
        "lat",
        "lng",
        "corregido",
    )
    list_filter = (
        "tipo",
        "origen",     # 👈 y aquí
        "corregido",
        "timestamp",
    )
    search_fields = (
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


# Reemplazamos el admin estándar de User por el nuestro
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
