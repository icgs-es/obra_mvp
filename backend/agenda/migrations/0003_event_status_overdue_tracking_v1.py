import django.utils.timezone
from django.db import migrations, models
from django.db.models import Q


def normalize_status_and_cutover(apps, schema_editor):
    Event = apps.get_model("agenda", "Event")
    cutoff = django.utils.timezone.now()

    Event.objects.filter(
        status__in=["PENDIENTE", "EN_PROCESO", "BLOQUEADA"]
    ).update(status="PROGRAMADO")

    Event.objects.filter(
        status="PROGRAMADO",
    ).filter(
        Q(end__gte=cutoff) | Q(end__isnull=True, start__gte=cutoff)
    ).update(seguimiento_atrasos_desde=cutoff)


def reverse_status(apps, schema_editor):
    Event = apps.get_model("agenda", "Event")
    Event.objects.filter(status="PROGRAMADO").update(status="PENDIENTE")


class Migration(migrations.Migration):
    dependencies = [
        ("agenda", "0002_event_team"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="seguimiento_atrasos_desde",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text=(
                    "Nulo para eventos históricos excluidos del seguimiento "
                    "de atrasos."
                ),
                null=True,
                verbose_name="Seguimiento de atrasos desde",
            ),
        ),
        migrations.RunPython(normalize_status_and_cutover, reverse_status),
        migrations.AlterField(
            model_name="event",
            name="status",
            field=models.CharField(
                choices=[
                    ("PROGRAMADO", "Programado"),
                    ("COMPLETADO", "Completado"),
                    ("CANCELADO", "Cancelado"),
                ],
                default="PROGRAMADO",
                max_length=20,
                verbose_name="Estado del evento",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="seguimiento_atrasos_desde",
            field=models.DateTimeField(
                blank=True,
                default=django.utils.timezone.now,
                editable=False,
                help_text=(
                    "Nulo para eventos históricos excluidos del seguimiento "
                    "de atrasos."
                ),
                null=True,
                verbose_name="Seguimiento de atrasos desde",
            ),
        ),
    ]
