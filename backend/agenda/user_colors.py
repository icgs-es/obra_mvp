# AGENDA_USER_COLORS_V1_3
# Presentación visual. No contiene reglas de acceso ni edición.

import re

FALLBACK_COLOR = "#3498DB"

_VISIBILITY = {
    "PRIVADA": {"label": "Privado", "icon": "🔒"},
    "DEPARTAMENTO": {"label": "Departamento", "icon": "👥"},
    "GLOBAL": {"label": "Global", "icon": "🌐"},
}


def normalize_color(value):
    raw = str(value or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", raw):
        return FALLBACK_COLOR
    return raw.upper()


def contrast_text_color(background):
    color = normalize_color(background)
    rgb = [int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]

    def linearize(channel):
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = [linearize(channel) for channel in rgb]
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    contrast_white = 1.05 / (luminance + 0.05)
    contrast_black = (luminance + 0.05) / 0.05
    return "#FFFFFF" if contrast_white >= contrast_black else "#111827"


def user_display_name(user):
    if not user:
        return "Usuario eliminado"
    full_name = (user.get_full_name() or "").strip()
    return full_name or user.get_username() or f"Usuario #{user.pk}"


def build_user_color_map():
    from django.apps import apps

    UserProfile = apps.get_model("usuarios", "UserProfile")
    result = {}
    for profile in UserProfile.objects.select_related("user").all():
        result[profile.user_id] = {
            "name": user_display_name(profile.user),
            "color": normalize_color(profile.color),
        }
    return result


def event_owner(event, user_map):
    user_id = getattr(event, "created_by_id", None)
    if user_id in user_map:
        return user_map[user_id]
    if user_id:
        return {"name": f"Usuario #{user_id}", "color": FALLBACK_COLOR}
    return {"name": "Usuario eliminado", "color": FALLBACK_COLOR}


def owner_from_user_id(user_id, user_map):
    if user_id in user_map:
        return user_map[user_id]
    if user_id:
        return {"name": f"Usuario #{user_id}", "color": FALLBACK_COLOR}
    return {"name": "Usuario eliminado", "color": FALLBACK_COLOR}


def owner_color_payload(user_id, user_map):
    owner = owner_from_user_id(user_id, user_map)
    color = normalize_color(owner.get("color"))
    return {
        "backgroundColor": color,
        "borderColor": color,
        "textColor": contrast_text_color(color),
    }


def owner_identity_payload(user_id, user_map):
    owner = owner_from_user_id(user_id, user_map)
    return {
        "owner_id": user_id,
        "owner_name": owner["name"],
        "owner_color": normalize_color(owner["color"]),
    }


def event_color_payload(event, user_map):
    return owner_color_payload(getattr(event, "created_by_id", None), user_map)


def event_identity_payload(event, user_map):
    identity = owner_identity_payload(
        getattr(event, "created_by_id", None),
        user_map,
    )
    visibility = _VISIBILITY.get(
        str(getattr(event, "visibility", "") or "").upper(),
        {"label": "Sin visibilidad", "icon": "•"},
    )
    return {
        **identity,
        "visibility_label": visibility["label"],
        "visibility_icon": visibility["icon"],
    }
