from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import RetryableError, PermanentError


# def repair():

# def handle()
def handle(event: dict) -> None:
    """Coordina reparación y notificación con estado durable."""

    inventory_path = "data/inventory.json"
    events_path = "data/events.json"

    # 1. Cargar inventario y validar nuevamente el evento.
    inventory = load(inventory_path)

    if not isinstance(inventory, dict):
        raise PermanentError("Inventario inválido")

    clean_event = validate(event, inventory)

    event_id = clean_event["event_id"]

    # 2. Cargar el ledger de eventos.
    ledger = load(events_path)

    if not isinstance(ledger, dict):
        raise PermanentError("Ledger de eventos inválido")

    # 3. Buscar o crear el registro del evento.
    if event_id not in ledger:
        record = {
            "event": clean_event,
            "attempts": 0,
            "repair_done": False,
            "repair_result": None,
            "notified": False,
            "status": "pending",
        }

        ledger[event_id] = record

    else:
        record = ledger[event_id]

        if not isinstance(record, dict):
            raise PermanentError("Registro de evento inválido")

        # Impedir reutilizar un event_id con otro contenido.
        if record.get("event") != clean_event:
            raise PermanentError(
                "event_id asociado a otro contenido"
            )

        # Comprobar la integridad del registro.
        if (
            type(record.get("attempts")) is not int
            or record["attempts"] < 0
            or type(record.get("repair_done")) is not bool
            or type(record.get("notified")) is not bool
        ):
            raise PermanentError("Estado del evento inválido")

        if record["notified"] and not record["repair_done"]:
            raise PermanentError("Estado del evento inconsistente")

        if record["repair_done"]:
            if record.get("repair_result") not in (
                "repaired",
                "already_ok",
            ):
                raise PermanentError("Resultado de reparación inválido")

        elif record.get("repair_result") is not None:
            raise PermanentError("Resultado de reparación inconsistente")

    # 4. Incrementar y persistir el contador de procesamiento.
    record["attempts"] += 1

    attempts = record["attempts"]
    simulate_failures = clean_event.get("simulate_failures", 0)

    # 5. Simular fallos antes de tocar los recursos.
    if attempts <= simulate_failures:
        record["status"] = "retry_pending"
        save(events_path, ledger)

        raise RetryableError("Fallo temporal simulado")

    # 6. Registrar el estado actual antes de continuar.
    if record["repair_done"] and record["notified"]:
        record["status"] = "completed"

    elif record["repair_done"]:
        record["status"] = "notification_pending"

    else:
        record["status"] = "repair_pending"

    save(events_path, ledger)

    # 7. Reparar solamente si todavía no se realizó.
    if not record["repair_done"]:

        resource_id = clean_event["resource_id"]
        resource = inventory.get(resource_id)

        if not isinstance(resource, dict):
            raise PermanentError("Recurso no disponible en inventario")

        result = repair(resource, clean_event["event_type"])

        if result not in ("repaired", "already_ok"):
            raise PermanentError("Resultado de reparación desconocido")

        record["repair_result"] = result
        record["repair_done"] = True
        record["status"] = "notification_pending"

        # Persistir la reparación antes de notificar.
        save(events_path, ledger)

    # 8. Notificar solamente si todavía no se realizó.
    if not record["notified"]:

        summary = (
            f"Fénix: evento {event_id} procesado. "
            f"Tipo: {clean_event['event_type']}. "
            f"Recurso: {clean_event['resource_id']}. "
            f"Reparación: {record['repair_result']}."
        )

        notify(summary)

        record["notified"] = True
        record["status"] = "completed"

        # Persistir la notificación antes de retornar.
        save(events_path, ledger)

    # Si termina normalmente, el worker podrá ejecutar ACK.
    return None