from django.contrib import admin

from .models import (
    AccesoConversacionIA,
    ConversacionIA,
    MensajeIA,
)


class MensajeIAInline(admin.TabularInline):
    model = MensajeIA
    extra = 0

    readonly_fields = (
        "rol",
        "contenido",
        "proveedor",
        "modelo",
        "request_id",
        "tokens_entrada",
        "tokens_salida",
        "metadata",
        "created_at",
    )

    can_delete = False


class AccesoConversacionIAInline(
    admin.TabularInline
):
    model = AccesoConversacionIA
    extra = 0

    readonly_fields = (
        "user",
        "shared_by",
        "created_at",
    )

    can_delete = True


@admin.register(ConversacionIA)
class ConversacionIAAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titulo",
        "user",
        "estado",
        "updated_at",
    )

    list_filter = (
        "estado",
        "created_at",
    )

    search_fields = (
        "titulo",
        "user__username",
        "user__first_name",
        "user__last_name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = (
        AccesoConversacionIAInline,
        MensajeIAInline,
    )


@admin.register(MensajeIA)
class MensajeIAAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversacion",
        "rol",
        "proveedor",
        "modelo",
        "created_at",
    )

    list_filter = (
        "rol",
        "proveedor",
        "created_at",
    )

    search_fields = (
        "contenido",
        "request_id",
        "conversacion__titulo",
    )

    readonly_fields = (
        "created_at",
    )


@admin.register(AccesoConversacionIA)
class AccesoConversacionIAAdmin(
    admin.ModelAdmin
):
    list_display = (
        "id",
        "conversacion",
        "user",
        "shared_by",
        "created_at",
    )

    search_fields = (
        "conversacion__titulo",
        "user__username",
        "user__first_name",
        "user__last_name",
    )

    readonly_fields = (
        "created_at",
    )
