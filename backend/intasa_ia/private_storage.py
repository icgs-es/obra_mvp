import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_ia_root():
    return os.path.abspath(
        getattr(
            settings,
            "INTASA_IA_PRIVATE_ROOT",
            "/app/private_media/intasa_ia",
        )
    )


class PrivateIAStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", private_ia_root())
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Los adjuntos de INTASA IA no tienen URL pública.")


private_ia_storage = PrivateIAStorage()
