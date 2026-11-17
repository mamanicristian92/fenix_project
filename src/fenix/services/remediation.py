import logging
from typing import Dict, Any, Literal

from botocore.exceptions import ClientError 
from fenix.config.settings import client 
from fenix.utils.state import load, save 
from fenix.services.events import validate 
from fenix.services.notifications import notify 
from fenix.utils.errors import RetryableError, PermanentError 


logger = logging.getLogger(__name__)

def repair(
    resource: Dict[str, Any], event_type: str
) -> Literal["repaired", "already_ok"]:
    """Ejecuta la acción de reparación convergente sobre el recurso simulado

    usando Boto3[cite: 1, 2].

    Escenarios soportados:
    - EC2: Verifica el estado de la instancia (node-01) y la inicia si está
    detenida[cite: 1, 2].
    - S3: Verifica las etiquetas del bucket (bucket-01) y las restaura si
    faltan[cite: 1, 2].

    Args:
        resource (dict): Datos del recurso provenientes del inventario.
        event_type (str): Tipo de evento o falla detectada.

    Returns:
        str: "repaired" si se aplicaron cambios, o "already_ok" si el recurso
        ya se encontraba íntegro.

    Raises:
        PermanentError: Si el recurso no existe o el tipo no está soportado.
        RetryableError: Si la instancia se encuentra en un estado transitorio.
    """
    resource_type = resource.get("type")
    resource_identifier = resource.get("identifier")

    # Validar que los atributos esenciales del recurso estén presentes
    if not resource_type or not resource_identifier:
        raise PermanentError(
            "El recurso provisto no contiene tipo o identificador válido."
        )

    # Escenario 1: EC2 (Garantizar estado 'running' en node-01)[cite: 1, 2]
    if resource_type == "ec2":
        instance_id = resource_identifier

        try:
            response = client.ec2.describe_instances(InstanceIds=[instance_id])
            reservations = response.get("Reservations", [])
        except ClientError as err:
            raise PermanentError(
                f"Error de Boto3 al consultar la instancia EC2 {instance_id}: {err}"
            )

        if not reservations or not reservations[0].get("Instances"):
            raise PermanentError(
                f"Instancia EC2 {instance_id} no encontrada en AWS/LocalStack."
            )

        instance_state = reservations[0]["Instances"][0]["State"]["Name"]

        # Evaluar convergencia según el estado actual de la instancia
        if instance_state == "running":
            logger.info(
                f"Instancia EC2 {instance_id} ya se encuentra en estado 'running'."
            )
            return "already_ok"
        elif instance_state == "stopped":
            logger.info(
                f"Iniciando instancia EC2 {instance_id} para restaurar estado 'running'..."
            )
            client.ec2.start_instances(InstanceIds=[instance_id])
            return "repaired"
        elif instance_state in ("stopping", "pending", "shutting-down"):
            logger.warning(
                f"Instancia EC2 {instance_id} en estado transitorio '{instance_state}'."
            )
            raise RetryableError(
                f"Instancia EC2 en estado transitorio: {instance_state}"
            )
        else:
            raise PermanentError(
                f"Estado de instancia EC2 desconocido: {instance_state}"
            )

    # Escenario 2: S3 (Restaurar etiquetas obligatorias en bucket-01)[cite: 1, 2]
    elif resource_type == "s3":
        bucket_name = resource_identifier
        expected_tags = resource.get(
            "tags", {"Environment": "production", "Project": "Fenix"}
        )

        try:
            response = client.s3.get_bucket_tagging(Bucket=bucket_name)
            current_tags_list = response.get("TagSet", [])
            current_tags = {
                tag["Key"]: tag["Value"] for tag in current_tags_list
            }
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code in ("NoSuchTagSet", "TagSetNotFound"):
                current_tags = {}
            else:
                raise PermanentError(
                    f"Error de Boto3 al obtener etiquetas del bucket S3 {bucket_name}: {err}"
                )

        # Verificar convergencia comparando diccionarios de etiquetas
        if current_tags == expected_tags:
            logger.info(
                f"Bucket S3 {bucket_name} ya posee las etiquetas obligatorias."
            )
            return "already_ok"
        else:
            logger.info(
                f"Aplicando etiquetas obligatorias al bucket S3 {bucket_name}..."
            )
            tag_set = [
                {"Key": k, "Value": v} for k, v in expected_tags.items()
            ]
            client.s3.put_bucket_tagging(
                Bucket=bucket_name, Tagging={"TagSet": tag_set}
            )
            return "repaired"

    # Manejar escenarios de recursos no reconocidos
    else:
        raise PermanentError(
            f"Tipo de recurso desconocido en inventario: {resource_type}"
        )


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