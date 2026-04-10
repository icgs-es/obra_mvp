from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator

User = settings.AUTH_USER_MODEL


class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    nombre_fiscal = models.CharField(max_length=255, blank=True, default="")
    nif = models.CharField(max_length=20, blank=True, default="")
    direccion = models.CharField(max_length=255, blank=True, default="")
    codigo_postal = models.CharField(max_length=10, blank=True, default="")
    poblacion = models.CharField(max_length=100, blank=True, default="")
    provincia = models.CharField(max_length=100, blank=True, default="")
    members = models.ManyToManyField(User, related_name="teams", blank=True)
    leads = models.ManyToManyField(User, related_name="teams_led", blank=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    color = models.CharField(
        max_length=7,
        default="#3498DB",  # changed from "#2D6CDF" to "#3498DB"
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message="El color debe estar en formato hex (#RRGGBB)",
            )
        ],
    )

    def __str__(self):
        return f"Perfil de {getattr(self.user, 'username', self.user_id)}"

