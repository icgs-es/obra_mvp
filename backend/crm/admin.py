from django.contrib import admin
from .models import Lead, Prospect, Cliente, LeadActivity, FuenteLead, Activo

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "nombre", "telefono", "email", "fuente", "estado", "agente", "fecha")
    list_filter = ("team", "estado", "fuente", "agente")
    search_fields = ("nombre", "telefono", "email")

@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = ("id", "lead")
    search_fields = ("lead__nombre", "lead__email", "lead__telefono")

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("id", "lead")
    search_fields = ("lead__nombre", "lead__email", "lead__telefono")

@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "lead", "user", "fecha")
    search_fields = ("descripcion", "lead__nombre", "user__username")


@admin.register(FuenteLead)
class FuenteLeadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "team")
    search_fields = ("nombre",)


@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "team")
    search_fields = ("nombre",)