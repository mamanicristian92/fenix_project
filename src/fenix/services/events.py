"""Contrato de eventos del TP (integrante 1).

Define el esquema estricto que deben cumplir los eventos de infraestructura
y la verificación de que el recurso referenciado pertenece al inventario
autorizado, antes de cualquier efecto sobre la nube.
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text


class EventModel(BaseModel):
    """Esquema estricto de un evento de infraestructura.

    Acepta únicamente los campos declarados (extra="forbid") y sin
    coerción de tipos (strict=True). Reglas locales:

    - schema_version: el entero 1; no admite True, 1.0 ni "1".
    - event_id y resource_id: identificadores cortos según identifier().
    - event_type: "instance.stopped" o "bucket.tags_missing".
    - occurred_at: fecha ISO 8601 con UTC explícito según utc_text().
    - simulate_failures: entero entre 0 y 5, sin coerción.

    La validación no modifica la entrada ni produce efectos externos;
    solo construye una instancia con los campos ya verificados.

    Raises:
        pydantic.ValidationError: Si falta un campo obligatorio, sobra
            una clave o algún valor no cumple el tipo o las reglas.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # StrictInt con ge=1 y le=1 exige el entero 1: Literal[1] aceptaba
    # True y 1.0 por comparación de igualdad, incluso en modo estricto.
    schema_version: StrictInt = Field(ge=1, le=1)
    event_id: str
    event_type: Literal["instance.stopped", "bucket.tags_missing"]
    resource_id: str
    occurred_at: str
    simulate_failures: StrictInt = Field(ge=0, le=5)

    @field_validator("event_id", "resource_id")
    @classmethod
    def validate_identifiers(cls, value):
        """Aplica el contrato de identifier() a event_id y resource_id.

        Args:
            value: Texto recibido para el campo; debe cumplir el patrón
                [a-z0-9-]{3,32} (minúsculas, dígitos y guiones).

        Returns:
            El mismo texto, sin normalizar, cuando cumple el formato.

        Raises:
            ValidationError: Si value no es texto o no cumple el patrón;
                pydantic la envuelve como error de campo del modelo.

        No modifica la entrada ni produce efectos secundarios.
        """
        return identifier(value)

    @field_validator("occurred_at")
    @classmethod
    def validate_date(cls, value):
        """Exige que occurred_at sea una fecha UTC explícita.

        Args:
            value: Texto de fecha ISO 8601 terminado en "Z" o "+00:00".

        Returns:
            El texto original sin transformar, para conservar el evento
            tal como llegó; utc_text() solo se usa como verificación.

        Raises:
            ValidationError: Si value no es texto, no declara UTC o no
                es una fecha válida; pydantic la envuelve como error de
                campo del modelo.

        No modifica la entrada ni produce efectos secundarios.
        """
        utc_text(value)
        return value


def validate(event: dict, inventory: dict) -> dict:
    """Valida un evento contra el esquema y el inventario autorizado.

    Comprueba en orden: que inventory sea un dict, que event cumpla el
    esquema de EventModel, que el alias resource_id exista en el
    inventario y que el tipo del recurso coincida con event_type
    ("instance.stopped" -> "ec2", "bucket.tags_missing" -> "s3").

    Args:
        event: Evento crudo recibido, con los campos del esquema.
        inventory: Inventario autorizado; mapea cada alias a un recurso
            con su clave "type".

    Returns:
        Un dict nuevo con los campos validados (model_dump), listo para
        el procesamiento posterior. Nunca devuelve None.

    Raises:
        ValidationError: Si el inventario no es un dict, el evento no
            cumple el esquema, el alias no está autorizado o el tipo de
            recurso no coincide con el evento.

    No modifica event ni inventory y no produce efectos externos.
    """

    if not isinstance(inventory, dict):
        raise ValidationError("Inventario inválido.")

    try:
        validated = EventModel.model_validate(event)
    except Exception as error:
        raise ValidationError("Evento inválido.") from error

    resource = inventory.get(validated.resource_id)

    if not isinstance(resource, dict):
        raise ValidationError("Recurso no autorizado.")

    expected_type = {
        "instance.stopped": "ec2",
        "bucket.tags_missing": "s3",
    }

    if resource.get("type") != expected_type[validated.event_type]:
        raise ValidationError("El evento no coincide con el recurso.")

    return validated.model_dump()
