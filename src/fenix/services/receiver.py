
import json
import logging
import os

from typing import Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from fenix.utils.crypto import verify
from fenix.services.sqs import publish, queue_url
from fenix.services.events import validate
from fenix.utils.errors import ValidationError
from fenix.utils.state import load


load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fénix Webhook Receiver",
    description="Endpoint seguro para recibir alertas de infraestructura, validar firmas HMAC y encolar eventos en SQS.",
    version="1.0.0",
)

# Cargar la clave secreta desde las variables de entorno.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PREFIX = os.getenv("QUEUE_PREFIX", "")


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(request: Request) -> Dict[str, str]:
    """
    Recibe un webhook, verifica su firma HMAC y valida el evento
    contra el inventario antes de publicarlo en SQS.

    El proceso comprueba que la cabecera de firma sea única y válida,
    que el cuerpo no supere los 16 KiB y que contenga JSON codificado
    en UTF-8. La firma se verifica considerando la ventana temporal
    de validez definida en crypto.verify().

    La validación del evento comprueba su estructura y que el recurso
    esté autorizado en el inventario. Las operaciones de SQS se ejecutan
    en un threadpool para no bloquear el endpoint asíncrono.

    Respuestas:
        202: Evento autenticado, validado y publicado.
        400: JSON inválido, UTF-8 incorrecto o Content-Length inválido.
        401: Firma ausente, duplicada, inválida o vencida.
        413: Cuerpo superior a 16 KiB.
        422: Evento inválido o recurso no autorizado.
        503: Clave secreta, inventario o servicio SQS no disponible.

    Retorna:
        Identificadores del evento y del mensaje publicado en SQS.
    """
    if not WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET no está configurada.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de autenticación no disponible.",
        )

    # Comprobar que exista una sola cabecera de firma.
    headers = request.headers.getlist("x-webhook-signature")

    if len(headers) != 1 or not headers[0].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma ausente o duplicada.",
        )

    # Parsear la cabecera y rechazar campos desconocidos o duplicados.
    try:
        header_parts = {}

        for item in headers[0].split(","):
            if "=" not in item:
                raise ValueError("Cabecera inválida.")

            key, value = item.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key not in ("t", "v1") or not value:
                raise ValueError("Campo inválido.")

            if key in header_parts:
                raise ValueError("Campo duplicado.")

            header_parts[key] = value

        if set(header_parts) != {"t", "v1"}:
            raise ValueError("Faltan campos.")

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabecera de firma inválida.",
        )

    # Comprobar el tamaño informado antes de leer el cuerpo.
    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            if int(content_length) > 16 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="El cuerpo supera el límite de 16 KiB.",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content-Length inválido.",
            )

    # Obtener el cuerpo y comprobar su tamaño real.
    body_bytes = await request.body()

    if len(body_bytes) > 16 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="El cuerpo supera el límite de 16 KiB.",
        )

    # Verificar la firma HMAC y su vigencia temporal.
    if not verify(
        secret=WEBHOOK_SECRET,
        timestamp=header_parts["t"],
        body=body_bytes,
        received_signature=header_parts["v1"],
    ):
        logger.warning("Firma HMAC inválida o vencida.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma de seguridad inválida.",
        )

    # Decodificar el cuerpo y comprobar que contiene JSON válido.
    try:
        payload_data = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cuerpo debe contener JSON válido en UTF-8.",
        )

    if not isinstance(payload_data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El payload debe ser un objeto JSON.",
        )

    # Validar la estructura del evento y la autorización del recurso.
    try:
        inventory = load("data/inventory.json")
        payload_data = validate(payload_data, inventory)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Evento o recurso inválido.",
        )
    except Exception:
        logger.exception("No se pudo cargar el inventario.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inventario no disponible.",
        )

    # Publicar en SQS sin bloquear el endpoint asíncrono.
    try:
        url = await run_in_threadpool(queue_url, PREFIX)
        message_id = await run_in_threadpool(publish, url, payload_data)
    except Exception:
        logger.exception("No se pudo publicar el evento en SQS.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo publicar el evento.",
        )

    logger.info("Evento %s publicado correctamente.", payload_data["event_id"])

    return {
        "status": "success",
        "message": "Alerta autenticada y encolada exitosamente en SQS.",
        "event_id": payload_data["event_id"],
        "message_id": message_id,
    }
