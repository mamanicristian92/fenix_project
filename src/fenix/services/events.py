from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text


class EventModel(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    schema_version: Literal[1]
    event_id: str
    event_type: Literal["instance.stopped", "bucket.tags_missing"]
    resource_id: str
    occurred_at: str
    simulate_failures: StrictInt = Field(ge=0, le=5)

    @field_validator("event_id", "resource_id")
    @classmethod
    def validate_identifiers(cls, value):
        return identifier(value)

    @field_validator("occurred_at")
    @classmethod
    def validate_date(cls, value):
        utc_text(value)
        return value


def validate(event: dict, inventory: dict) -> dict:

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