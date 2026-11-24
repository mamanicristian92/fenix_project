"""Contratos de validación a completar por el integrante 1."""

import re
from datetime import datetime, timezone, timedelta

from fenix.utils.errors import ValidationError


def identifier(value: str) -> str:
    """Valida un identificador corto de evento o recurso.

    Args:
        value: Texto a validar; debe cumplir el patrón [a-z0-9-]{3,32}
            (minúsculas, dígitos y guiones, entre 3 y 32 caracteres).

    Returns:
        El mismo texto recibido, sin normalizar ni recortar, cuando
        cumple el formato. Nunca devuelve None.

    Raises:
        ValidationError: Si value no es str o no cumple el patrón; por
            ejemplo rutas ("../AJENO"), mayúsculas o longitudes fuera
            del rango.

    No modifica la entrada ni produce efectos secundarios.
    """

    if not isinstance(value, str):
        raise ValidationError("El identificador debe ser texto.")

    if not re.fullmatch(r"[a-z0-9-]{3,32}", value):
        raise ValidationError("Formato de identificador inválido.")

    return value


def ttl_seconds(value: str) -> int:
    """Valida un TTL en segundos dentro del rango [60, 600].

    Args:
        value: Representación de un número entero de segundos, pensada
            para llegar como texto (por ejemplo "60"); se convierte con
            int(), sin redondear entradas decimales en texto.

    Returns:
        El entero convertido, cuando la conversión tiene éxito y el
        resultado está entre 60 y 600 inclusive. Nunca devuelve None.

    Raises:
        ValidationError: Si int() no puede convertir la entrada (texto
            no numérico o tipo no convertible) o si el entero resultante
            queda fuera del rango permitido.

    No modifica la entrada ni produce efectos secundarios.
    """

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
    """Interpreta una fecha ISO 8601 con UTC explícito.

    Args:
        value: Texto de fecha que termina en "Z" o "+00:00"; se
            interpreta con datetime.fromisoformat tras reemplazar la
            "Z" final por "+00:00".

    Returns:
        Un datetime consciente equivalente a la fecha recibida,
            expresado en UTC (offset 0). Nunca devuelve None.

    Raises:
        ValidationError: Si value no es str, no declara UTC mediante
            "Z" o "+00:00", no es una fecha ISO válida, carece de zona
            horaria o su offset respecto de UTC no es cero.

    No modifica la entrada ni produce efectos secundarios.
    """

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