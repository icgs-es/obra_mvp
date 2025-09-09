from django.db import models
from django.conf import settings

class Evento(models.Model):
    titulo = models.CharField(max_length=200)
    inicio = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    asistentes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="eventos")
    ubicacion = models.CharField(max_length=240, blank=True)
    notas = models.TextField(blank=True)
    recordatorio_min = models.PositiveIntegerField(default=0)  # 0 = sin recordatorio
    visibilidad = models.CharField(max_length=15, default="privada")  # privada|depto|global
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
