import django.utils.timezone
from django.db import migrations, models
from django.db.models import Q


def enable_future_tracking(apps, schema_editor):
    Tarea = apps.get_model("tareas", "Tarea")
    cutoff = django.utils.timezone.now()
    today = django.utils.timezone.localdate(cutoff)

    Tarea.objects.exclude(estado="hecha").filter(
        Q(fin_programado__gte=cutoff)
        | Q(fin_programado__isnull=True, inicio_programado__gte=cutoff)
        | Q(
            fin_programado__isnull=True,
            inicio_programado__isnull=True,
            vencimiento__gte=today,
        )
    ).update(seguimiento_atrasos_desde=cutoff)


class Migration(migrations.Migration):
    dependencies = [
        ("tareas", "0002_tarea_team_scope_v1"),
    ]

    operations = [
        migrations.AddField(
            model_name="tarea",
            name="inicio_programado",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Inicio con hora opcional para mostrar la tarea en Agenda."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tarea",
            name="fin_programado",
            field=models.DateTimeField(
                blank=True,
                help_text="Fin opcional de la programación horaria.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tarea",
            name="seguimiento_atrasos_desde",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text=(
                    "Nulo para tareas históricas excluidas del seguimiento "
                    "de atrasos."
                ),
                null=True,
            ),
        ),
        migrations.RunPython(enable_future_tracking, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tarea",
            name="seguimiento_atrasos_desde",
            field=models.DateTimeField(
                blank=True,
                default=django.utils.timezone.now,
                editable=False,
                help_text=(
                    "Nulo para tareas históricas excluidas del seguimiento "
                    "de atrasos."
                ),
                null=True,
            ),
        ),
    ]
