"""Contratos de validación a completar por el integrante 1."""

import re
from datetime import datetime, timezone, timedelta

from fenix.utils.errors import ValidationError


def identifier(value: str) -> str:
    """Valida un identificador corto."""

    if not isinstance(value, str):
        raise ValidationError("El identificador debe ser texto.")

    if not re.fullmatch(r"[a-z0-9-]{3,32}", value):
        raise ValidationError("Formato de identificador inválido.")

    return value


def ttl_seconds(value: str) -> int:
    """Valida un TTL entre 60 y 600 segundos."""

    try:
        ttl = int(value)
    except (ValueError, TypeError) as error:
        raise ValidationError(
            "El TTL debe ser un número entero."
        ) from error

    if not 60 <= ttl <= 600:
        raise ValidationError(
            "El TTL debe estar entre 60 y 600 segundos."
        )

    return ttl


def utc_text(value: str) -> datetime:
    """Interpreta una fecha UTC explícita."""

    if not isinstance(value, str):
        raise ValidationError("La fecha debe ser texto.")

    if not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValidationError(
            "La fecha debe indicar UTC mediante Z o +00:00."
        )

    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValidationError(
            "El formato de fecha no es válido."
        ) from error

    if result.tzinfo is None:
        raise ValidationError("La fecha debe incluir zona horaria.")

    if result.utcoffset() != timedelta(0):
        raise ValidationError("La fecha debe estar expresada en UTC.")

    return result.astimezone(timezone.utc)