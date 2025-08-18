from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone

#def __str__(self):
#    return f"{self.obra.codigo} · {self.codigo} · {self.nombre}" 

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: abstract = True

class Obra(TimeStampedModel):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=255)
    def __str__(self): return f"{self.codigo} · {self.nombre}"

class SubObra(TimeStampedModel):
    TIPO_CHOICES = [
        ("VIV", "Vivienda"),
        ("ZC", "Zona común"),
        ("FCH", "Fachada"),
        ("URB", "Urbanización"),
        ("JAR", "Jardines"),
        ("PIS", "Piscina"),
        ("OTR", "Otro"),
    ]
    ESTADO_CHOICES = [("plan", "Planificada"), ("activa", "Activa"), ("cerrada", "Cerrada")]

    obra = models.ForeignKey("Obra", on_delete=models.PROTECT, related_name="subobras")
    codigo = models.CharField(max_length=40)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=4, choices=TIPO_CHOICES, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default="plan")

    class Meta:
        unique_together = (("obra", "codigo"),)
        ordering = ("obra", "codigo")
        verbose_name = "Subobra"
        verbose_name_plural = "Subobras"

    def __str__(self):
        return f"{self.obra.codigo} · {self.codigo} · {self.nombre}"

class Capitulo(TimeStampedModel):
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='capitulos')
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=255)
    orden = models.PositiveIntegerField(default=0)
    presupuesto_plan = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    class Meta: unique_together = ('obra','codigo'); ordering=['obra','orden','codigo']
    # dentro de class Capitulo(...)
    subobra = models.ForeignKey("SubObra", on_delete=models.PROTECT, related_name="capitulos", null=True, blank=True)
    def __str__(self):
        obra = self.obra.codigo if getattr(self, "obra", None) else "-"
        sub  = self.subobra.codigo if getattr(self, "subobra", None) else "-"
        return f"{obra} · {sub} · {self.codigo} · {self.nombre}"

class RecursoPersonal(TimeStampedModel):
    nombre = models.CharField(max_length=255)
    especialidad = models.CharField(max_length=80, blank=True)
    coste_hora = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    activo = models.BooleanField(default=True)
    def __str__(self): return self.nombre

class RecursoMaterial(TimeStampedModel):
    referencia = models.CharField(max_length=80)
    nombre = models.CharField(max_length=255)
    unidad = models.CharField(max_length=20, default='ud')
    precio_ref = models.DecimalField(max_digits=12, decimal_places=4, default=0, validators=[MinValueValidator(0)])

class Tarea(TimeStampedModel):
    capitulo = models.ForeignKey(Capitulo, on_delete=models.CASCADE, related_name='tareas')
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    fecha_inicio_plan = models.DateField(null=True, blank=True)
    fecha_fin_plan = models.DateField(null=True, blank=True)
    horas_plan = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coste_plan = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    class Meta:
        verbose_name = "Partida"
        verbose_name_plural = "Partidas"

    def __str__(self):
        try:
            return f"{self.capitulo.codigo} · {self.nombre}"
        except Exception:
            return self.nombre

class Planificacion(TimeStampedModel):
    TIPO=[('PERSONAL','Personal'),('MATERIAL','Material')]
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name='planificaciones')
    fecha = models.DateField()
    tipo = models.CharField(max_length=10, choices=TIPO)
    recurso_personal = models.ForeignKey('RecursoPersonal', on_delete=models.SET_NULL, null=True, blank=True, related_name='planificaciones')
    recurso_material = models.ForeignKey('RecursoMaterial', on_delete=models.SET_NULL, null=True, blank=True, related_name='planificaciones')
    horas_plan = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cantidad_plan = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    importe_plan = models.DecimalField(max_digits=12, decimal_places=2, default=0)

class Ausencia(TimeStampedModel):
    TIPO=[('vacaciones','Vacaciones'),('baja','Baja'),('otro','Otro')]
    recurso = models.ForeignKey('RecursoPersonal', on_delete=models.CASCADE, related_name='ausencias')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    tipo = models.CharField(max_length=20, choices=TIPO, default='vacaciones')
    comentario = models.CharField(max_length=255, blank=True)

class Proveedor(TimeStampedModel):
    nombre = models.CharField(max_length=255)
    nif = models.CharField(max_length=20, blank=True)
    def __str__(self):
        return self.nombre

class FacturaProveedor(TimeStampedModel):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="facturas")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="facturas")
    capitulo = models.ForeignKey(Capitulo, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas")
    numero = models.CharField(max_length=80)
    fecha = models.DateField()
    base = models.DecimalField(max_digits=12, decimal_places=2)
    impuestos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=[("pendiente","Pendiente"),("pagada","Pagada")], default="pendiente")
    def __str__(self):
        return f"{self.numero} · {self.proveedor}"

class Vencimiento(TimeStampedModel):
    factura = models.ForeignKey(FacturaProveedor, on_delete=models.CASCADE, related_name="vencimientos")
    fecha_venc = models.DateField()
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    pagado = models.BooleanField(default=False)
    def __str__(self):
        return f"{self.fecha_venc} · {self.importe:.2f}"

class ParteTrabajo(TimeStampedModel):
    recurso = models.ForeignKey(RecursoPersonal, on_delete=models.PROTECT, related_name="partes")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="partes")
    capitulo = models.ForeignKey(Capitulo, on_delete=models.PROTECT, related_name="partes")
    tarea = models.ForeignKey(Tarea, on_delete=models.SET_NULL, null=True, blank=True, related_name="partes")
    fecha = models.DateField(default=timezone.now)
    horas = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    observaciones = models.CharField(max_length=255, blank=True)
