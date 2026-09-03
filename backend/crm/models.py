from django.db import models
from django.conf import settings
from usuarios.models import Team


class FuenteLead(models.Model):
    nombre = models.CharField(max_length=128)
    url = models.URLField(blank=True)
    usuario = models.CharField(max_length=128, blank=True)
    password = models.CharField(max_length=128, blank=True)
    observaciones = models.TextField(blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="crm_fuentes")

    def __str__(self):
        return self.nombre


class Activo(models.Model):
    nombre = models.CharField(max_length=128)
    direccion = models.CharField(max_length=255, blank=True)
    cod_postal = models.CharField(max_length=16, blank=True)
    ciudad = models.CharField(max_length=128, blank=True)
    provincia = models.CharField(max_length=128, blank=True)
    observaciones = models.TextField(blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="crm_activos")

    def __str__(self):
        return self.nombre


class Lead(models.Model):
    ESTADO_CHOICES = [
        ('nuevo', 'Nuevo'),
        ('prospeccion', 'Prospección'),
        ('cliente', 'Cliente'),
    ]
    TIPO_ACTIVO_CHOICES = [
        ("mensaje", "Mensaje"),
        ("llamada", "Llamada"),
    ]
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="crm_leads",related_query_name="crm_lead")
    agente = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads_as_agente")
    fuente = models.ForeignKey(FuenteLead, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    fecha = models.DateField(null=True, blank=True)
    activo = models.ForeignKey(Activo, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    tipo_activo = models.CharField(max_length=24, choices=TIPO_ACTIVO_CHOICES, blank=True)
    precio = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    dorm = models.CharField(max_length=32, blank=True)
    interes = models.TextField(blank=True)
    activo_lead = models.BooleanField(default=True)
    nombre = models.CharField(max_length=128)
    telefono = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    seatable = models.BooleanField(default=False)
    inmovilla = models.BooleanField(default=False)
    contestada = models.BooleanField(default=False)
    contestada_at = models.DateField(null=True, blank=True)
    seatable_at = models.DateField(null=True, blank=True)
    inmovilla_at = models.DateField(null=True, blank=True)
    visita = models.BooleanField(default=False)
    visita_at = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=24, choices=ESTADO_CHOICES, default='nuevo')
    notas = models.TextField(blank=True)

    class Meta:
        unique_together = [
            ("team", "email"),
            ("team", "telefono"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.email or self.telefono})"

class Prospect(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="crm_prospects", related_query_name="crm_prospect")
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="prospect")
    notas = models.TextField(blank=True)

class Cliente(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="crm_clientes", related_query_name="crm_cliente")
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="cliente")
    notas = models.TextField(blank=True)

class LeadActivity(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True)
    descripcion = models.TextField()