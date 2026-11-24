import json
import logging
import os
from dotenv import load_dotenv

from typing import Any, Dict
from fastapi import FastAPI, Header, HTTPException, Request, status  # type: ignore[import-not-found]
from fenix.utils.crypto import verify
from fenix.services.sqs import publish
from fenix.services.sqs import queue_url


# Intentar importar el servicio de SQS (desarrollado por I2).
# Si aún no está disponible, se define un stub para evitar fallos de ejecución.

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fénix Webhook Receiver",
    description="Endpoint seguro para recibir alertas de infraestructura, validar firmas HMAC y encolar eventos en SQS.",
    version="1.0.0",
)

# Carga de la clave secreta desde las variables de entorno del sistema
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PREFIX = os.getenv("QUEUE_PREFIX", "")

@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)


async def receive_webhook(
    request: Request,
    # Se permite que la solicitud llegue al receptor sin esta cabecera
    # para gestionar la ausencia de firma y responder con HTTP 401.
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> Dict[str, str]:
    """
    Recibe, autentica y procesa webhooks de alertas de infraestructura.

    Flujo de ejecución:
        1. Verifica que WEBHOOK_SECRET esté configurada.
        2. Comprueba la cabecera X-Webhook-Signature.
        3. Extrae el timestamp y la firma HMAC-SHA256.
        4. Obtiene el cuerpo original en bytes y verifica la firma.
        5. Decodifica el cuerpo y valida que sea un objeto JSON.
        6. Publica el evento autenticado en Amazon SQS.

    Args:
        request: Solicitud HTTP de FastAPI.
        x_webhook_signature: Cabecera opcional con el formato
            "t={timestamp},v1={digest}".

    Returns:
        Dict[str, str]: Confirmación de que el evento fue encolado.

    Raises:
        HTTPException:
            400: El cuerpo no contiene JSON válido.
            401: Falta la firma o no es válida.
            422: El JSON recibido no es un objeto.
            500: Error de configuración o procesamiento interno.
    """
    if not WEBHOOK_SECRET:
        logger.error("La variable de entorno WEBHOOK_SECRET no está configurada.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de configuración interna del servidor.",
        )

    # 1. Parsear la cabecera unificada X-Webhook-Signature (Formato: "t=1700000000,v1=abcdef...")
    if not x_webhook_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la firma de seguridad.",
        )
    try:
        header_parts = {}

        for item in x_webhook_signature.split(","):
            item = item.strip()

            if not item or "=" not in item:
                raise ValueError("Componente de cabecera inválido.")

            key, value = item.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key not in ("t", "v1") or not value:
                raise ValueError("Campo desconocido o vacío.")

            if key in header_parts:
                raise ValueError("Campo duplicado.")

            header_parts[key] = value

        if set(header_parts) != {"t", "v1"}:
            raise ValueError("Faltan campos obligatorios.")

        x_timestamp = header_parts["t"]
        x_signature = header_parts["v1"]

    except ValueError:
        x_timestamp, x_signature = None, None

    try:
        # 2. Obtener el cuerpo de la petición en formato de bytes crudos
        body_bytes = await request.body()

        # 3. Validar la firma HMAC usando crypto.py
        is_valid = verify(
            secret=WEBHOOK_SECRET,
            timestamp=x_timestamp,
            body=body_bytes,
            received_signature=x_signature,
        )

        if not is_valid:
            logger.warning("Intento de webhook rechazado: Firma HMAC inválida o alterada.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firma de seguridad inválida.",
            )

        # 4. Decodificar y validar que el cuerpo sea un JSON estructurado
        try:
            payload_data = json.loads(body_bytes.decode("utf-8"))

            if not isinstance(payload_data, dict):
                logger.warning("El payload JSON debe ser un objeto.")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="El payload debe ser un objeto JSON.",
                )

        except json.JSONDecodeError:
            logger.error("El payload recibido no posee un formato JSON válido.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El payload debe ser un objeto JSON válido.",
            )

        logger.info(f"Webhook autenticado correctamente. Evento: {payload_data.get('event_type', 'desconocido')}")

        # 5. Encolar el mensaje en SQS para su procesamiento asíncrono
        publish(queue_url(PREFIX), payload_data)

        return {
            "status": "success",
            "message": "Alerta autenticada y encolada exitosamente en SQS.",
        }

    except HTTPException:
        # Re-lanzar excepciones HTTP previamente controladas
        raise
    except Exception as e:
        logger.exception(f"Error inesperado al procesar el webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno procesando la alerta.",
        )
