from django.db import models
from django.conf import settings
from django.utils import timezone
from usuarios.models import Team

class Tarea(models.Model):
    ESTADOS = [
        ("pendiente","Pendiente"),
        ("en_curso","En curso"),
        ("bloqueada","Bloqueada"),
        ("hecha","Hecha"),
    ]
    PRIORIDAD = [("baja","Baja"),("media","Media"),("alta","Alta")]

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tareas_portal",
    )
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD, default="media")
    vencimiento = models.DateField(null=True, blank=True)
    inicio_programado = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Inicio con hora opcional para mostrar la tarea en Agenda.",
    )
    fin_programado = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fin opcional de la programación horaria.",
    )
    seguimiento_atrasos_desde = models.DateTimeField(
        null=True,
        blank=True,
        default=timezone.now,
        editable=False,
        help_text=(
            "Nulo para tareas históricas excluidas del seguimiento de atrasos."
        ),
    )
    creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="tareas_creadas")
    asignados = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tareas_asignadas", blank=True)
    etiquetas = models.CharField(max_length=250, blank=True)
    modulo_origen = models.CharField(max_length=30, default="manual")
    visibilidad = models.CharField(max_length=15, default="privada")  # privada|depto|global
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo

    @property
    def is_completed(self):
        return self.estado == "hecha"

    def is_overdue_at(self, moment=None):
        """Evalúa hora programada o vencimiento al final del día local."""
        if self.seguimiento_atrasos_desde is None or self.is_completed:
            return False

        moment = moment or timezone.now()
        programmed_end = self.fin_programado or self.inicio_programado

        if programmed_end is not None:
            return programmed_end < moment

        if self.vencimiento is not None:
            return self.vencimiento < timezone.localdate(moment)

        return False

    @property
    def is_overdue(self):
        return self.is_overdue_at()

class ParteTiempo(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="partes")
    fecha = models.DateField()
    minutos = models.PositiveIntegerField(default=0)
    nota = models.CharField(max_length=280, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

class Timer(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tarea = models.ForeignKey(Tarea, on_delete=models.SET_NULL, null=True, blank=True)
    inicio = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=False)
