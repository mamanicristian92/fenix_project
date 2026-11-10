
"""Adaptador de notificaciones externas mediante Telegram."""

import logging
import os

import requests

from fenix.utils.errors import PermanentError, RetryableError


logger = logging.getLogger(__name__)

MAX_RETRY_AFTER_SECONDS = 30


def _bounded_retry_after(value: str | None) -> float | None:
    """Interpreta Retry-After y limita la espera indicada a 30 segundos."""
    if value is None:
        return None

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None

    return min(max(seconds, 0), MAX_RETRY_AFTER_SECONDS)


def notify(text: str) -> None:
    """Envía una notificación a Telegram y confirma su aceptación."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # Comprobar que existan las credenciales.
    if not token or not chat_id:
        raise PermanentError(
            "Falta configurar TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID."
        )

    if not isinstance(text, str) or not text.strip():
        raise PermanentError("El mensaje de notificación está vacío o es inválido.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text[:1000],
    }

    # Enviar la solicitud sin exponer el token en los registros.
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=(2, 5),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        logger.warning(
            "Fallo de conexión con Telegram",
            extra={
                "action": "telegram_notify",
                "status": "connection_error",
            },
        )
        raise RetryableError(
            "No se pudo establecer comunicación con Telegram."
        ) from None
    except requests.RequestException:
        logger.warning(
            "Error HTTP al comunicarse con Telegram",
            extra={
                "action": "telegram_notify",
                "status": "request_error",
            },
        )
        raise RetryableError(
            "Ocurrió un error de comunicación con Telegram."
        ) from None

    status_code = response.status_code

    # Error 429: límite de solicitudes alcanzado.
    if status_code == 429:
        retry_after = _bounded_retry_after(
            response.headers.get("Retry-After")
        )

        error = RetryableError(
            "Telegram aplicó un límite de solicitudes (HTTP 429). "
            f"Retry-After acotado: {retry_after} segundos."
        )
        error.retry_after = retry_after
        raise error

    # Error 5xx: problema temporal del servidor.
    if 500 <= status_code <= 599:
        retry_after = _bounded_retry_after(
            response.headers.get("Retry-After")
        )

        error = RetryableError(
            f"Telegram presenta un error temporal HTTP {status_code}. "
            f"Retry-After acotado: {retry_after} segundos."
        )
        error.retry_after = retry_after
        raise error

    # Otros errores 4xx: rechazo definitivo.
    if 400 <= status_code <= 499:
        raise PermanentError(
            f"Telegram rechazó la solicitud (HTTP {status_code})."
        )

    # Cualquier respuesta distinta de 2xx no contemplada.
    if not 200 <= status_code < 300:
        raise RetryableError(
            f"Respuesta HTTP inesperada de Telegram: {status_code}."
        )

    # Comprobar la respuesta JSON del proveedor.
    try:
        data = response.json()
    except ValueError:
        raise RetryableError(
            "Telegram devolvió una respuesta que no contiene JSON válido."
        ) from None

    # HTTP 200 no garantiza que Telegram haya aceptado el mensaje.
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise PermanentError(
            "Telegram rechazó funcionalmente la notificación."
        )

    logger.info(
        "Notificación enviada correctamente a Telegram",
        extra={
            "action": "telegram_notify",
            "status": "success",
        },
    )

    return None
