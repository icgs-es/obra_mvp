from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    members = models.ManyToManyField(User, related_name="teams", blank=True)
    leads = models.ManyToManyField(User, related_name="teams_led", blank=True)

    def __str__(self):
        return self.name
