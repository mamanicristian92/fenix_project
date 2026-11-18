"""Plantilla central de integración: un worker, un mensaje por vez."""
import json  # Convierte Body solo dentro del control por mensaje.
import time  # Evita un bucle intensivo si el emulador no responde.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.services.sqs import receive, acknowledge, retry_later
from fenix.utils.errors import ProjectError


def get_receive_count(message: dict) -> int | None:
    """Obtiene la cantidad de entregas informada por SQS."""
    if not isinstance(message, dict):
        return None

    attributes = message.get("Attributes")

    if not isinstance(attributes, dict):
        return None

    raw_count = attributes.get("ApproximateReceiveCount")

    try:
        receive_count = int(raw_count)
    except (TypeError, ValueError):
        return None

    if receive_count < 1:
        return None

    return receive_count


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes SQS, ejecuta el handler y gestiona ACK y reintentos"""
    handled_errors = (
        BotoCoreError,
        ClientError,
        ProjectError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
    )
    while True:
        # 1. Consultar SQS.
        try:
            messages = receive(url)

        except NotImplementedError:
            raise

        except handled_errors as error:
            logger.error(
                "Fallo al consultar SQS: %s",
                type(error).__name__,
                extra={
                    "action": "worker_receive",
                    "status": "error",
                },
            )
            if once:
                return None

            time.sleep(2)
            continue

        # 2. Procesar los mensajes recibidos.
        for message in messages:

            message_id = "unknown"
            event_id = None
            resource_id = None
            receipt = None
            receive_count = get_receive_count(message)

            log_context = {
                "message_id": message_id,
                "event_id": event_id,
                "resource_id": resource_id,
                "receive_count": receive_count,
            }
            try:
                if not isinstance(message, dict):
                    raise ProjectError("Mensaje SQS inválido")

                message_id = message.get("MessageId", "unknown")
                if not isinstance(message_id, str) or not message_id.strip():
                    message_id = "unknown"

                log_context["message_id"] = message_id

                receipt = message.get("ReceiptHandle")

                if not isinstance(receipt, str) or not receipt.strip():
                    raise ProjectError("Mensaje SQS sin ReceiptHandle válido")

                body = message.get("Body")

                # El evento debe ser un objeto JSON.
                if not isinstance(body, str) or not body:
                    raise ProjectError("Mensaje SQS sin Body válido")

                event = json.loads(body)

                if not isinstance(event, dict):
                    raise ProjectError(
                        "El mensaje debe contener un objeto JSON"
                    )

                # Obtener contexto sin registrar el contenido completo.
                event_id = event.get("event_id")
                resource_id = event.get("resource_id")

                if not isinstance(event_id, str):
                    event_id = None

                if not isinstance(resource_id, str):
                    resource_id = None

                log_context.update({
                    "event_id": event_id,
                    "resource_id": resource_id,
                })
                # Ejecutar el procesamiento de negocio.
                handler(event)

            except NotImplementedError:
                raise
            except handled_errors as error:
                logger.error(
                    "Fallo al procesar mensaje: %s",
                    type(error).__name__,
                    extra={
                        **log_context,
                        "action": "worker_process",
                        "status": "error",
                    },
                )
                if not isinstance(receipt, str) or not receipt.strip():
                    continue

                # 3. No hubo procesamiento exitoso.
                # Programar una nueva oportunidad de entrega.
                try:
                    delay_seconds = retry_later(url, message)
                    logger.warning(
                        "Mensaje programado para reintento en %s segundos",
                        delay_seconds,
                        extra={
                            **log_context,
                            "action": "worker_retry",
                            "status": "warning",
                        }
                    )
                except NotImplementedError:
                    raise
                except handled_errors as retry_error:
                    logger.error(
                        "No se pudo programar el reintento: %s",
                        type(retry_error).__name__,
                        extra={
                            **log_context,
                            "action": "worker_retry",
                            "status": "error",
                        },
                    )
                    if not once:
                        time.sleep(2)
                continue
            # 4. El handler terminó normalmente.
            # Ahora podemos confirmar el mensaje.
            try:
                acknowledge(url, receipt)
            except NotImplementedError:
                raise
            except handled_errors as error:
                logger.error(
                    "Fallo al confirmar el mensaje: %s",
                    type(error).__name__,
                    extra={
                        **log_context,
                        "action": "worker_ack",
                        "status": "error",
                    }
                )
                if not once:
                    time.sleep(2)
                continue
            # 5. Confirmación exitosa.
            logger.info(
                "Mensaje confirmado correctamente",
                extra={
                    **log_context,
                    "action": "worker_ack",
                    "status": "success",
                },
            )
        # 6. En modo once, terminar después de una consulta.
        if once:
            return None
