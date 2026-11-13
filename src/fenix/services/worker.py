"""Plantilla central de integración: un worker, un mensaje por vez."""
import json  # Convierte Body solo dentro del control por mensaje.
import time  # Evita un bucle intensivo si el emulador no responde.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.services.sqs import receive, acknowledge, retry_later
from fenix.utils.errors import ProjectError


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes y confirma únicamente resultados durables."""

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

            message_id = message.get("MessageId", "unknown")
            event_id = None
            resource_id = None

            try:
                # Decodificar el cuerpo JSON.
                event = json.loads(message["Body"])

                # El evento debe ser un objeto JSON.
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

                # Ejecutar el procesamiento de negocio.
                handler(event)

            except NotImplementedError:
                raise

            except handled_errors as error:

                logger.error(
                    "Fallo al procesar mensaje: %s",
                    type(error).__name__,
                    extra={
                        "action": "worker_process",
                        "status": "error",
                        "message_id": message_id,
                        "event_id": event_id,
                        "resource_id": resource_id,
                    },
                )

                # 3. No hubo procesamiento exitoso.
                # Programar una nueva oportunidad de entrega.
                try:
                    delay_seconds = retry_later(url, message)

                    logger.warning(
                        "Mensaje programado para reintento en %s segundos",
                        delay_seconds,
                        extra={
                            "action": "worker_retry",
                            "status": "retry_scheduled",
                            "message_id": message_id,
                            "event_id": event_id,
                            "resource_id": resource_id,
                        },
                    )

                except NotImplementedError:
                    raise

                except handled_errors as retry_error:

                    logger.error(
                        "No se pudo programar el reintento: %s",
                        type(retry_error).__name__,
                        extra={
                            "action": "worker_retry",
                            "status": "error",
                            "message_id": message_id,
                        },
                    )

                    if not once:
                        time.sleep(2)

                continue

            # 4. El handler terminó normalmente.
            # Ahora podemos confirmar el mensaje.
            try:
                acknowledge(url, message["ReceiptHandle"])

            except NotImplementedError:
                raise

            except handled_errors as error:

                logger.error(
                    "Fallo al confirmar el mensaje: %s",
                    type(error).__name__,
                    extra={
                        "action": "worker_ack",
                        "status": "error",
                        "message_id": message_id,
                        "event_id": event_id,
                        "resource_id": resource_id,
                    },
                )

                if not once:
                    time.sleep(2)

                continue

            # 5. Confirmación exitosa.
            logger.info(
                "Mensaje confirmado correctamente",
                extra={
                    "action": "worker_ack",
                    "status": "success",
                    "message_id": message_id,
                    "event_id": event_id,
                    "resource_id": resource_id,
                },
            )

        # 6. En modo once, terminar después de una consulta.
        if once:
            return None
