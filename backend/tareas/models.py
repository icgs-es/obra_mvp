from django.db import models
from django.conf import settings

class Tarea(models.Model):
    ESTADOS = [
        ("pendiente","Pendiente"),
        ("en_curso","En curso"),
        ("bloqueada","Bloqueada"),
        ("hecha","Hecha"),
    ]
    PRIORIDAD = [("baja","Baja"),("media","Media"),("alta","Alta")]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD, default="media")
    vencimiento = models.DateField(null=True, blank=True)
    creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="tareas_creadas")
    asignados = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tareas_asignadas", blank=True)
    etiquetas = models.CharField(max_length=250, blank=True)
    modulo_origen = models.CharField(max_length=30, default="manual")
    visibilidad = models.CharField(max_length=15, default="privada")  # privada|depto|global
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo

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
