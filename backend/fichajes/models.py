import re
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

User = get_user_model()

class Fichaje(models.Model):
    TIPO_CHOICES = [
        ("IN", "Entrada jornada"),
        ("OUT", "Salida jornada"),
        ("PAUSA_IN", "Inicio pausa"),
        ("PAUSA_OUT", "Fin pausa"),
        ("OTRO_IN", "Inicio permiso corto"),
        ("OTRO_OUT", "Fin permiso corto"),
    ]

    ORIGEN_CHOICES = [
        ("PORTAL", "Portal web"),
        ("TERMINAL", "Terminal PIN"),
        ("OTRO", "Otro"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fichajes",
    )
    team = models.ForeignKey(
        "usuarios.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fichajes",
        help_text="Empresa/Team a la que pertenece este fichaje.",
    )

    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES)
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Fecha/hora del servidor en la que se realiza el fichaje.",
    )

    # Datos técnicos
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Geolocalización (si el navegador lo permite)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Gestión y auditoría
    observaciones = models.TextField(blank=True)
    corregido = models.BooleanField(default=False)
    corregido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="fichajes_corregidos",
        on_delete=models.SET_NULL,
    )
    motivo_correccion = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    location_text = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Lugar (texto geolocalización)",
    )
    
    origen = models.CharField(
        max_length=10,
        choices=ORIGEN_CHOICES,
        default="PORTAL",
        db_index=True,
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "fichaje"
        verbose_name_plural = "fichajes"

    def __str__(self):
        return f"{self.user} - {self.get_tipo_display()} - {self.timestamp}"

    @property
    def maps_url(self):
        if self.lat is None or self.lng is None:
            return ""
        return f"https://www.google.com/maps?q={self.lat},{self.lng}"

    @property
    def short_location(self):
        """
        Devuelve una versión corta y legible del lugar.

        Preferimos, para España:
          - "Rincón de la Victoria, Málaga, España"
        o, si no se puede, algo tipo:
          - "29738, Málaga, España"
        """
        if self.location_text:
            parts = [p.strip() for p in self.location_text.split(",") if p.strip()]
            n = len(parts)
            if n == 0:
                return ""

            country = parts[-1]

            # Lista simple de comunidades autónomas para "saltar" la región
            AUTONOMIAS = {
                "Andalucía",
                "Comunidad de Madrid",
                "Cataluña",
                "Castilla y León",
                "Castilla-La Mancha",
                "Comunitat Valenciana",
                "Galicia",
                "País Vasco",
                "Aragón",
                "Región de Murcia",
                "Extremadura",
                "Cantabria",
                "La Rioja",
                "Principado de Asturias",
                "Navarra",
                "Islas Baleares",
                "Illes Balears",
                "Canarias",
                "Ceuta",
                "Melilla",
            }

            # ¿Hay un código postal de 5 dígitos en la dirección?
            postcode = None
            for p in parts:
                if re.fullmatch(r"\d{5}", p):
                    postcode = p
                    break

            # Si hay CP, usamos CP + provincia + país
            # Ej: "... , Málaga, Andalucía, 29738, España"
            if postcode:
                # Buscamos la provincia inmediatamente antes del CP, si existe
                try:
                    idx = parts.index(postcode)
                except ValueError:
                    idx = -1

                province = None
                if idx > 0:
                    province = parts[idx - 1]

                if province:
                    return f"{postcode}, {province}, {country}"
                else:
                    return f"{postcode}, {country}"

            # Si no hay CP, intentamos ciudad + provincia + país
            # Patrón típico:
            #   Calle, barrio, ciudad, comarca, provincia, comunidad, país
            #   -> ciudad = -5, provincia = -3
            if n >= 7 and parts[-2] in AUTONOMIAS:
                city = parts[-5]   # Rincón de la Victoria
                province = parts[-3]  # Málaga
                return f"{city}, {province}, {country}"

            # Patrón algo más corto:
            #   ..., ciudad, provincia, comunidad, país
            if n >= 5 and parts[-2] in AUTONOMIAS:
                city = parts[-3]
                province = parts[-2]  # aquí la autonomía, preferimos provincia si la tenemos
                # si hay más niveles, province podría estar un poco antes; lo simplificamos:
                return f"{city}, {province}, {country}"

            # Si todo lo anterior falla, usamos las 3 últimas partes como antes
            if n >= 3:
                return ", ".join(parts[-3:])

            # Último recurso
            return self.location_text

        # Si no hay location_text, usamos coordenadas cortas
        if self.lat is not None and self.lng is not None:
            return f"{float(self.lat):.5f}, {float(self.lng):.5f}"

        return ""


    @staticmethod
    def calcular_resumen_dia(user, fecha=None):
        """
        Devuelve:
          - horas_efectivas (float): horas trabajadas descontando pausas y permisos
          - fichajes_del_dia (QuerySet)
          - estado_actual: 'dentro', 'fuera', 'pausa', 'permiso'
        """

        if fecha is None:
            fecha = timezone.localdate()

        qs = (
            Fichaje.objects
            .filter(user=user, timestamp__date=fecha)
            .order_by("timestamp")
        )

        if not qs.exists():
            return 0.0, qs, "fuera"

        total_jornada_seg = 0
        total_pausa_seg = 0
        total_permiso_seg = 0

        inicio_jornada = None
        inicio_pausa = None
        inicio_permiso = None

        estado_actual = "fuera"

        hoy = timezone.localdate()
        ahora = timezone.now()

        for f in qs:
            if f.tipo == "IN":
                # Abrimos tramo de jornada si no había uno abierto
                if inicio_jornada is None:
                    inicio_jornada = f.timestamp
                estado_actual = "dentro"

            elif f.tipo == "OUT":
                if inicio_jornada is not None:
                    total_jornada_seg += (f.timestamp - inicio_jornada).total_seconds()
                    inicio_jornada = None
                estado_actual = "fuera"

            elif f.tipo == "PAUSA_IN":
                if inicio_pausa is None:
                    inicio_pausa = f.timestamp
                estado_actual = "pausa"

            elif f.tipo == "PAUSA_OUT":
                if inicio_pausa is not None:
                    total_pausa_seg += (f.timestamp - inicio_pausa).total_seconds()
                    inicio_pausa = None
                estado_actual = "dentro" if inicio_jornada is not None else "fuera"

            elif f.tipo == "OTRO_IN":
                if inicio_permiso is None:
                    inicio_permiso = f.timestamp
                estado_actual = "permiso"

            elif f.tipo == "OTRO_OUT":
                if inicio_permiso is not None:
                    total_permiso_seg += (f.timestamp - inicio_permiso).total_seconds()
                    inicio_permiso = None
                estado_actual = "dentro" if inicio_jornada is not None else "fuera"

        # Si es hoy, contabilizamos tramos abiertos hasta "ahora"
        if fecha == hoy:
            if inicio_jornada is not None:
                total_jornada_seg += (ahora - inicio_jornada).total_seconds()
            if inicio_pausa is not None:
                total_pausa_seg += (ahora - inicio_pausa).total_seconds()
            if inicio_permiso is not None:
                total_permiso_seg += (ahora - inicio_permiso).total_seconds()

        # Horas efectivas = jornada - pausas - permisos
        total_efectivo_seg = total_jornada_seg - total_pausa_seg - total_permiso_seg
        if total_efectivo_seg < 0:
            total_efectivo_seg = 0

        horas_efectivas = round(total_efectivo_seg / 3600.0, 2)

        return horas_efectivas, qs, estado_actual


class Ausencia(models.Model):
    TIPO_CHOICES = [
        ("VACACIONES", "Vacaciones"),
        ("PERMISO", "Permiso retribuido"),
        ("PERMISO_NR", "Permiso no retribuido"),
        ("BAJA", "Baja médica"),
        ("ASUNTOS", "Asuntos propios"),
        ("FORMACION", "Formación"),
        ("OTRA", "Otra ausencia"),
    ]

    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
    ]

    empleado = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ausencias"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    horas = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Opcional, para medias jornadas u horas sueltas",
    )
    motivo = models.TextField(blank=True)
    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES, default="PENDIENTE"
    )
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ausencias_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"{self.empleado} - {self.tipo} {self.fecha_inicio} → {self.fecha_fin}"

from django.core.validators import RegexValidator

class TerminalFichaje(models.Model):
    """
    PIN personal para fichar desde el terminal (tablet) sin acceder al portal.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="terminal_fichaje",
    )

    pin = models.CharField(
        max_length=4,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^\d{4}$",
                message="El PIN debe tener exactamente 4 dígitos numéricos.",
            )
        ],
        help_text="PIN de 4 dígitos para fichar en el terminal.",
    )

    activo = models.BooleanField(default=True)
    descripcion = models.CharField(
        max_length=255,
        blank=True,
        help_text="Opcional: nota interna (p.ej. Departamento, puesto…).",
    )

    class Meta:
        verbose_name = "PIN de fichaje"
        verbose_name_plural = "PINs de fichaje"

    def __str__(self):
        return f"{self.user} — PIN terminal"
