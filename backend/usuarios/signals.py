from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


User = get_user_model()


@receiver(
    post_save,
    sender=User,
    dispatch_uid=(
        "usuarios_crear_perfil_usuario_v1"
    ),
)
def crear_perfil_usuario(
    sender,
    instance,
    created,
    **kwargs,
):
    if created:
        UserProfile.objects.get_or_create(
            user=instance
        )
