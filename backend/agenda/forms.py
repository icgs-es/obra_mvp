from django import forms
from django.utils import timezone
from .models import Event


class MultiFileInput(forms.ClearableFileInput):
    # Necesario en Django 4+ para permitir multiple=True
    allow_multiple_selected = True


ESTADO_TAREA_CHOICES = (
    ("PENDIENTE", "Pendiente"),
    ("EN_PROCESO", "En proceso"),
    ("BLOQUEADA", "Bloqueada"),
    ("COMPLETADO", "Completado"),
    ("CANCELADO", "Cancelado"),
)

VISIBILIDAD_CHOICES = (
    ("privada", "Privada"),
    ("depto", "Departamento"),
    ("global", "Global"),
)


class EventoForm(forms.ModelForm):
    # ---- CAMPOS EXTRA (no son de modelo) ----
    visibilidad = forms.ChoiceField(
        choices=VISIBILIDAD_CHOICES,
        required=False,
        label="Visibilidad",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="privada · depto · global",
    )

    recordatorio_min = forms.IntegerField(
        required=False,
        min_value=0,
        label="Recordatorio (minutos antes)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "5"}),
        help_text="Minutos antes del inicio (0 = sin recordatorio).",
    )

    adjuntos = forms.FileField(
        label="Archivos adjuntos",
        required=False,
        widget=MultiFileInput(
            attrs={"multiple": True, "class": "form-control"}
        ),
    )

    class Meta:
        model = Event
        # 👇 SOLO campos que existen en models.Event
        fields = [
            "title",
            "calendar",
            "start",
            "end",
            "all_day",
            "rrule",
            "rrule_until",
            "who_text",
            "who_users",
            "description",
            "status",
            "location",
        ]
        labels = {
            "title": "Título",
            "calendar": "Calendario",
            "start": "Desde",
            "end": "Hasta",
            "all_day": "Todo el día",
            "rrule": "Se repite (RRULE)",
            "rrule_until": "Repetir hasta",
            "who_text": "Quién (texto libre)",
            "who_users": "Usuarios asignados",
            "description": "Descripción / notas",
            "status": "Estado tarea",
            "location": "Dónde",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Título del evento"}
            ),
            "calendar": forms.Select(
                attrs={"class": "form-select"}
            ),
            "start": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "end": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "all_day": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "rrule": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "FREQ=WEEKLY;BYDAY=MO,WE",
                }
            ),
            "rrule_until": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "who_text": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombres, teléfonos o externos",
                }
            ),
            "who_users": forms.SelectMultiple(
                attrs={"class": "form-select", "size": "6"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Notas del evento...",
                }
            ),
            "status": forms.Select(
                attrs={"class": "form-select"}
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Sala / Dirección / Link",
                }
            ),
        }

    def clean(self):
        data = super().clean()
        tz = timezone.get_current_timezone()

        def to_aware(val):
            if not val:
                return val
            if timezone.is_aware(val):
                return val
            return timezone.make_aware(val, tz)

        start = to_aware(data.get("start"))
        end = to_aware(data.get("end"))
        rrule_until = to_aware(data.get("rrule_until"))

        if not start:
            self.add_error("start", "Debes indicar la fecha/hora de inicio.")
            return data

        # Si all_day y sin fin → fin = inicio
        if data.get("all_day") and not end:
            end = start

        if end and end < start:
            self.add_error("end", "La fecha/hora de fin no puede ser anterior al inicio.")

        if rrule_until and rrule_until < start:
            self.add_error("rrule_until", "La fecha 'Repetir hasta' no puede ser anterior al inicio.")

        data["start"] = start
        data["end"] = end
        data["rrule_until"] = rrule_until

        return data

    def save(self, commit=True):
        """
        Aquí puedes aprovechar para usar recordatorio_min, visibilidad, adjuntos, etc.
        Por ahora solo guardamos el Event; la lógica extra la puedes añadir más adelante.
        """
        instance = super().save(commit=False)

        # Aquí podrías hacer algo con:
        # self.cleaned_data.get("recordatorio_min")
        # self.cleaned_data.get("visibilidad")
        # self.cleaned_data.get("adjuntos")

        if commit:
            instance.save()
            self.save_m2m()

        return instance
