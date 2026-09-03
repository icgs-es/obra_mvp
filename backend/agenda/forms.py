from django import forms
from django.utils import timezone

from .access import (
    assignee_queryset_for_event,
    available_calendars_for_event,
    calendar_matches_visibility,
)
from .models import Event


class MultiFileInput(
    forms.ClearableFileInput
):
    allow_multiple_selected = True


class EventoForm(forms.ModelForm):
    recordatorio_min = forms.IntegerField(
        required=False,
        min_value=0,
        label=(
            "Recordatorio "
            "(minutos antes)"
        ),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0",
                "step": "5",
            }
        ),
        help_text=(
            "Minutos antes del inicio "
            "(0 = sin recordatorio)."
        ),
    )

    adjuntos = forms.FileField(
        label="Archivos adjuntos",
        required=False,
        widget=MultiFileInput(
            attrs={
                "multiple": True,
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = Event

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
            "visibility",
        ]

        labels = {
            "title": "Título",
            "calendar": "Calendario",
            "start": "Desde",
            "end": "Hasta",
            "all_day": "Todo el día",
            "rrule": "Se repite (RRULE)",
            "rrule_until": (
                "Repetir hasta"
            ),
            "who_text": (
                "Quién (texto libre)"
            ),
            "who_users": (
                "Usuarios asignados"
            ),
            "description": (
                "Descripción / notas"
            ),
            "status": "Estado del evento",
            "location": "Dónde",
        }

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Título del evento"
                    ),
                }
            ),
            "calendar": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "start": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "end": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "all_day": (
                forms.CheckboxInput(
                    attrs={
                        "class": (
                            "form-check-input"
                        ),
                    }
                )
            ),
            "rrule": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "FREQ=WEEKLY;"
                        "BYDAY=MO,WE"
                    ),
                }
            ),
            "rrule_until": (
                forms.DateTimeInput(
                    attrs={
                        "type": (
                            "datetime-local"
                        ),
                        "class": (
                            "form-control"
                        ),
                    },
                    format=(
                        "%Y-%m-%dT%H:%M"
                    ),
                )
            ),
            "who_text": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Nombres, teléfonos "
                        "o externos"
                    ),
                }
            ),
            "who_users": (
                forms.SelectMultiple(
                    attrs={
                        "class": (
                            "form-select"
                        ),
                        "size": "6",
                    }
                )
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Notas del evento..."
                    ),
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Sala / Dirección / Link"
                    ),
                }
            ),
            "visibility": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        team=None,
        **kwargs,
    ):
        instance = kwargs.get(
            "instance"
        )

        if args and args[0] is not None:
            submitted = args[0].copy()
            if submitted.get("status") in {
                "PENDIENTE",
                "EN_PROCESO",
                "BLOQUEADA",
            }:
                submitted["status"] = Event.Status.PROGRAMADO
            args = (submitted, *args[1:])

        super().__init__(
            *args,
            **kwargs,
        )

        self.user = user
        self.team = team

        self.fields[
            "calendar"
        ].queryset = (
            available_calendars_for_event(
                user=user,
                instance=instance,
            )
        )

        self.fields[
            "who_users"
        ].queryset = (
            assignee_queryset_for_event(
                user=user,
                team=team,
                instance=instance,
            )
        )

        datetime_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
        ]

        for name in (
            "start",
            "end",
            "rrule_until",
        ):
            field = self.fields.get(
                name
            )

            if field is not None:
                field.input_formats = (
                    datetime_formats
                )

        if instance is not None:
            tz = (
                timezone
                .get_current_timezone()
            )

            date_format = (
                "%Y-%m-%dT%H:%M"
            )

            for name in (
                "start",
                "end",
                "rrule_until",
            ):
                value = getattr(
                    instance,
                    name,
                    None,
                )

                if value:
                    self.fields[
                        name
                    ].initial = (
                        value
                        .astimezone(tz)
                        .strftime(
                            date_format
                        )
                    )

    def clean_who_users(self):
        users = self.cleaned_data.get(
            "who_users"
        )

        if users is None:
            return users

        if self.team is not None:
            invalid = users.exclude(
                teams=self.team
            )

            if invalid.exists():
                raise forms.ValidationError(
                    (
                        "Hay asistentes que no "
                        "pertenecen a la empresa "
                        "del evento."
                    ),
                    code=(
                        "cross_team_attendee"
                    ),
                )

        return users

    def clean(self):
        data = super().clean()

        tz = (
            timezone
            .get_current_timezone()
        )

        def to_aware(value):
            if not value:
                return value

            if timezone.is_aware(
                value
            ):
                return value

            return timezone.make_aware(
                value,
                tz,
            )

        start = to_aware(
            data.get("start")
        )

        end = to_aware(
            data.get("end")
        )

        rrule_until = to_aware(
            data.get("rrule_until")
        )

        if not start:
            self.add_error(
                "start",
                (
                    "Debes indicar la "
                    "fecha/hora de inicio."
                ),
            )

            return data

        if (
            data.get("all_day")
            and not end
        ):
            end = start

        if end and end < start:
            self.add_error(
                "end",
                (
                    "La fecha/hora de fin "
                    "no puede ser anterior "
                    "al inicio."
                ),
            )

        if (
            rrule_until
            and rrule_until < start
        ):
            self.add_error(
                "rrule_until",
                (
                    "La fecha 'Repetir hasta' "
                    "no puede ser anterior "
                    "al inicio."
                ),
            )

        calendar = data.get(
            "calendar"
        )

        visibility = data.get(
            "visibility"
        )

        if (
            calendar is not None
            and visibility
            and not calendar_matches_visibility(
                calendar,
                visibility,
                user=self.user,
            )
        ):
            self.add_error(
                "calendar",
                forms.ValidationError(
                    (
                        "El calendario no "
                        "corresponde con la "
                        "visibilidad seleccionada."
                    ),
                    code=(
                        "calendar_visibility_mismatch"
                    ),
                ),
            )

        data["start"] = start
        data["end"] = end
        data[
            "rrule_until"
        ] = rrule_until

        return data

    def save(self, commit=True):
        instance = super().save(
            commit=False
        )

        if commit:
            instance.save()
            self.save_m2m()

        return instance
