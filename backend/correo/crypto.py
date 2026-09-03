import json
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


DEFAULT_SECRET_FILE = "/app/infra/secrets/correo_intasa.json"


class CorreoCryptoError(RuntimeError):
    """Error seguro relacionado con el cifrado de credenciales."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    secret_path = Path(
        os.environ.get(
            "INTASA_CORREO_SECRET_FILE",
            DEFAULT_SECRET_FILE,
        )
    )

    try:
        payload = json.loads(
            secret_path.read_text(encoding="utf-8")
        )
        key = payload["fernet_key"].encode("ascii")
        return Fernet(key)
    except Exception as exc:
        raise CorreoCryptoError(
            "La clave maestra de INTASA Correo no está disponible."
        ) from exc


def encrypt_password(raw_password: str) -> str:
    if not raw_password:
        raise CorreoCryptoError(
            "No se puede cifrar una contraseña vacía."
        )

    return _get_fernet().encrypt(
        raw_password.encode("utf-8")
    ).decode("ascii")


def decrypt_password(encrypted_password: str) -> str:
    if not encrypted_password:
        raise CorreoCryptoError(
            "La cuenta no tiene una contraseña configurada."
        )

    try:
        return _get_fernet().decrypt(
            encrypted_password.encode("ascii")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise CorreoCryptoError(
            "La credencial cifrada no es válida."
        ) from exc
