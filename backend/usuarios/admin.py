from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from django.utils.html import format_html

from .models import Team, UserProfile


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("members","leads")


class UserProfileAdminForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = "__all__"
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"})
        }


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = (
        "user",
        "empresa_documental_predeterminada",
        "color_preview",
        "color",
    )
    search_fields = (
        "user__username",
        "user__email",
    )
    list_filter = (
        "empresa_documental_predeterminada",
    )

    def color_preview(self, obj):
        return format_html(
            '<span style="display:inline-block;width:20px;height:20px;background:{};border-radius:3px;"></span>',
            obj.color
        )

    color_preview.short_description = "Preview"


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    extra = 0


User = get_user_model()

# Reemplazar el UserAdmin por defecto para añadir el inline de perfil
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]

