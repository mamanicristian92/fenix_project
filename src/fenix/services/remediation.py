import logging
import os
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
    resource_identifier = resource.get("id")

    # Validar que los atributos esenciales del recurso estén presentes
    if not resource_type or not resource_identifier:
        raise PermanentError(
            "El recurso provisto no contiene tipo o identificador válido."
        )

    # Escenario 1: EC2 (Garantizar estado 'running' en node-01)[cite: 1, 2]
    if resource_type == "ec2":
        instance_id = resource_identifier

        try:
            response = client("ec2").describe_instances(InstanceIds=[instance_id])
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

            # Obtener el cliente EC2 para realizar las operaciones sobre la instancia.
            ec2_client = client("ec2")

            # Solicitar el inicio de la instancia que se encuentra detenida.
            ec2_client.start_instances(InstanceIds=[instance_id])

            # Consultar nuevamente el estado para comprobar si el inicio se completó.
            verification = ec2_client.describe_instances(
                InstanceIds=[instance_id]
            )

            # Extraer las reservas devueltas por EC2.
            reservations = verification.get("Reservations", [])

            # Si no se encuentra la instancia, no es posible confirmar la reparación.
            if not reservations or not reservations[0].get("Instances"):
                raise PermanentError(
                    f"No se pudo verificar la instancia EC2 {instance_id}."
                )

            # Obtener el estado actual informado por EC2 después del inicio.
            verified_state = (
                reservations[0]["Instances"][0]["State"]["Name"]
            )

            # No confirmar la reparación mientras la instancia no esté en running.
            if verified_state != "running":
                raise RetryableError(
                    f"La instancia EC2 {instance_id} todavía no está running. "
                    f"Estado actual: {verified_state}"
                )

            # Registrar que la instancia alcanzó el estado esperado.
            logger.info(
                f"Instancia EC2 {instance_id} verificada correctamente en running."
            )

            # Confirmar la reparación únicamente después de verificar running.
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

        # Obtener las etiquetas que deben existir según el inventario.
        expected_tags = resource.get("expected_tags")

        if not isinstance(expected_tags, dict) or not expected_tags:
            raise PermanentError("El recurso no contiene expected_tags válidos.")

        # Crear el cliente S3 para consultar y modificar el bucket.
        s3_client = client("s3")

        try:
            # Consultar las etiquetas que ya tiene el bucket.
            response = s3_client.get_bucket_tagging(Bucket=bucket_name)

            current_tags_list = response.get("TagSet", [])

            # Convertir la lista de etiquetas en un diccionario.
            current_tags = {
                tag["Key"]: tag["Value"] for tag in current_tags_list
            }

        except ClientError as err:
            # Un bucket sin etiquetas todavía puede repararse.
            error_code = err.response.get("Error", {}).get("Code", "")

            if error_code in ("NoSuchTagSet", "TagSetNotFound"):
                current_tags = {}
            else:
                raise PermanentError(
                    f"Error de Boto3 al obtener etiquetas del bucket S3 "
                    f"{bucket_name}: {err}"
                )

        # Copiar las etiquetas existentes para conservar las ajenas.
        merged_tags = current_tags.copy()

        # Incorporar o actualizar únicamente las etiquetas esperadas.
        merged_tags.update(expected_tags)

        # Si el resultado coincide con las etiquetas actuales, no modificar.
        if merged_tags == current_tags:
            logger.info(
                f"Bucket S3 {bucket_name} ya posee las etiquetas esperadas."
            )
            return "already_ok"

        logger.info(
            f"Actualizando etiquetas del bucket S3 {bucket_name}..."
        )

        # Convertir el diccionario combinado al formato requerido por S3.
        tag_set = [
            {"Key": key, "Value": value}
            for key, value in merged_tags.items()
        ]

        try:
            # Guardar las etiquetas sin eliminar las que no pertenecen al inventario.
            s3_client.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={"TagSet": tag_set}
            )

            # Volver a consultar para comprobar que la escritura fue correcta.
            verification = s3_client.get_bucket_tagging(Bucket=bucket_name)

            verified_tags = {
                tag["Key"]: tag["Value"]
                for tag in verification.get("TagSet", [])
            }

        except ClientError as err:
            raise PermanentError(
                f"No se pudieron guardar o verificar las etiquetas "
                f"del bucket S3 {bucket_name}: {err}"
            )

        # Confirmar que todas las etiquetas esperadas quedaron correctamente aplicadas.
        if verified_tags != merged_tags:
            raise RetryableError(
                f"No se pudo verificar la actualización de etiquetas "
                f"del bucket S3 {bucket_name}."
            )

        # Confirmar la reparación únicamente después de verificar la escritura.
        logger.info(
            f"Etiquetas del bucket S3 {bucket_name} verificadas correctamente."
        )

        return "repaired"

    # Manejar escenarios de recursos no reconocidos
    else:
        raise PermanentError(
            f"Tipo de recurso desconocido en inventario: {resource_type}"
        )


# ============================= def handle() ==================================
def handle(event: dict) -> None:
    """Coordina reparación y notificación con estado durable."""

    inventory_path = "data/inventory.json"
    events_path = "data/events.json"

    # 1. Cargar inventario y validar nuevamente el evento.
    inventory = load(inventory_path)

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

        if not isinstance(record.get("event"), dict):
            raise PermanentError("Evento almacenado inválido.")
        # Impedir reutilizar un event_id con otro contenido.
        if record.get("event") != clean_event:
            raise PermanentError(
                "event_id asociado a otro contenido"
            )
        valid_statuses = (
            "pending",
            "retry_pending",
            "repair_pending",
            "notification_pending",
            "completed"
        )
        if record.get("status") not in valid_statuses:
            raise PermanentError("Estado del evento inválido")
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

        if record["status"] == "completed":
            if not record["repair_done"] or not record["notified"]:
                raise PermanentError("Estado del evento inconsistente")

        if record["status"] == "notification_pending":
            if not record["repair_done"] or record["notified"]:
                raise PermanentError("Estado del evento inconsistente")

        if record["status"] in (
            "pending",
            "retry_pending",
            "repair_pending",
        ):
            if record["repair_done"] or record["notified"]:
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
    if not record["repair_done"] and attempts <= simulate_failures:
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

        provider = os.getenv("NOTIFY_PROVIDER", "console").strip().lower()

        if provider == "console":
            print(summary)

        elif provider == "telegram":
            if (
                os.getenv("TELEGRAM_BOT_TOKEN")
                and os.getenv("TELEGRAM_CHAT_ID")
            ):
                notify(summary)
            else:
                raise PermanentError("Faltan credenciales de Telegram")

        elif provider == "slack":
            raise PermanentError("Integracion con Slack no implementada")

        else:
            raise PermanentError("Proveedor de notificaion no valido")

        record["notified"] = True
        record["status"] = "completed"
        save(events_path, ledger)
