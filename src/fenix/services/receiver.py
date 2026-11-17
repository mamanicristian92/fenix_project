import json
import logging
import os
from typing import Any, Dict
from fastapi import FastAPI, Header, HTTPException, Request, status
from fenix.utils.crypto import verify_signature

# Intentar importar el servicio de SQS (desarrollado por I2).
# Si aún no está disponible, se define un stub para evitar fallos de ejecución.
try:
    from fenix.services.sqs import send_message_to_queue
except ImportError:
    def send_message_to_queue(payload: Dict[str, Any]) -> None:
        """Stub temporal para encolar mensajes si el módulo SQS no está cargado."""
        pass

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fénix Webhook Receiver",
    description="Endpoint seguro para recibir alertas de infraestructura, validar firmas HMAC y encolar eventos en SQS.",
    version="1.0.0",
)

# Carga de la clave secreta desde las variables de entorno del sistema
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    request: Request,
    x_webhook_signature: str = Header(..., alias="X-Webhook-Signature"),
) -> Dict[str, str]:
    """Endpoint HTTP POST para la recepción y autenticación de webhooks de alerta.

    Flujo de ejecución:
    1. Verifica la existencia de la clave secreta en el entorno.
    2. Extrae y parsea los componentes 't' (timestamp) y 'v1' (firma) de X-Webhook-Signature.
    3. Obtiene el payload en bytes y valida la autenticidad con HMAC SHA-256 (Anti-Replay).
    4. Decodifica el cuerpo a JSON estructurado.
    5. Publica el evento validado en Amazon SQS para procesamiento asíncrono.

    Args:
        request (Request): Objeto de solicitud HTTP de FastAPI para obtener el body crudo.
        x_webhook_signature (str): Cabecera con la firma unificada ("t={timestamp},v1={digest}").

    Returns:
        Dict[str, str]: Respuesta de confirmación con estado de encolamiento (202 Accepted).

    Raises:
        HTTPException:
            - 401 UNAUTHORIZED: Si la cabecera está malformada o la firma es inválida.
            - 400 BAD_REQUEST: Si el cuerpo de la petición no es un JSON válido.
            - 500 INTERNAL_SERVER_ERROR: Si falla la configuración o el encolamiento.
    """
    if not WEBHOOK_SECRET:
        logger.error("La variable de entorno WEBHOOK_SECRET no está configurada.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de configuración interna del servidor.",
        )

    # 1. Parsear la cabecera unificada X-Webhook-Signature (Formato: "t=1700000000,v1=abcdef...")
    try:
        header_parts = dict(
            item.split("=", 1) for item in x_webhook_signature.split(",") if "=" in item
        )
        x_timestamp = header_parts.get("t")
        x_signature = header_parts.get("v1")
    except Exception:
        x_timestamp, x_signature = None, None

    if not x_timestamp or not x_signature:
        logger.warning("Intento de webhook rechazado: Cabecera X-Webhook-Signature malformada.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de la cabecera X-Webhook-Signature inválido.",
        )

    try:
        # 2. Obtener el cuerpo de la petición en formato de bytes crudos
        body_bytes = await request.body()

        # 3. Validar la firma HMAC usando crypto.py
        is_valid = verify_signature(
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
        except json.JSONDecodeError:
            logger.error("El payload recibido no posee un formato JSON válido.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El payload debe ser un objeto JSON válido.",
            )

        logger.info(f"Webhook autenticado correctamente. Evento: {payload_data.get('event_type', 'desconocido')}")

        # 5. Encolar el mensaje en SQS para su procesamiento asíncrono
        send_message_to_queue(payload_data)

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
