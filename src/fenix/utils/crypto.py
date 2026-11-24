import hashlib
import hmac
import re
import time

from typing import Union


def signature(
    secret: Union[str, bytes],
    timestamp: Union[int, str],
    body: Union[str, bytes],
) -> str:
    """
    Genera una firma HMAC-SHA256 combinando el timestamp y el cuerpo
    original del webhook.

    El timestamp forma parte del contenido firmado para vincular la
    firma al momento de emisión de la solicitud. La protección contra
    ataques de repetición se aplica posteriormente mediante la
    validación temporal realizada por verify().

    Args:
        secret (Union[str, bytes]): Clave secreta compartida (WEBHOOK_SECRET).
        timestamp (Union[int, str]): Marca de tiempo de la petición HTTP.
        body (Union[str, bytes]): Cuerpo original del evento recibido.

    Returns:
        str: Firma hexadecimal de 64 caracteres calculada mediante HMAC-SHA256.
    """
    # Asegurar que la clave secreta esté en formato de bytes
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
        
    # Asegurar que el cuerpo de la petición esté en formato de bytes
    if isinstance(body, str):
        body = body.encode("utf-8")

    # Vincular el timestamp al cuerpo para que ambos formen parte de la firma HMAC.
    message = f"{timestamp}.".encode("utf-8") + body
    
    # Retornar el resumen hash hexadecimal calculado con HMAC-SHA256
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def generate_signature(
    secret: Union[str, bytes], 
    payload: Union[str, bytes]
) -> str:
    """
    Función auxiliar o alias para generar una firma directa basada únicamente en el payload.
    
    Utilizada en escenarios de prueba o componentes donde no se requiere 
    estrictamente la validación del timestamp por cabecera.

    Args:
        secret (Union[str, bytes]): Clave secreta compartida (WEBHOOK_SECRET).
        payload (Union[str, bytes]): Datos o cuerpo del mensaje a firmar.

    Returns:
        str: Firma hexadecimal de 64 caracteres.
    """
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
        
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
        
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()



def verify(
    secret: Union[str, bytes],
    timestamp: Union[int, str],
    body: Union[str, bytes],
    received_signature: str,
) -> bool:
    """
    Verifica la autenticidad de una firma HMAC-SHA256 y la vigencia
    temporal de una solicitud.

    Acepta timestamps Unix como enteros o cadenas de dígitos decimales,
    siempre que estén dentro de una ventana de ±300 segundos respecto
    al reloj del sistema.

    Rechaza timestamps inválidos, fuera de la ventana temporal o firmas
    incorrectas. Compara la firma esperada con la recibida mediante
    hmac.compare_digest() para reducir riesgos de ataques de temporización.

    Args:
        secret: Clave secreta compartida.
        timestamp: Timestamp Unix de la solicitud, en segundos.
        body: Cuerpo original de la petición.
        received_signature: Firma HMAC recibida.

    Returns:
        bool: True si el timestamp y la firma son válidos; False en caso contrario.
    """
    if not received_signature or not isinstance(received_signature, str):
        return False

    # Parseo estricto: únicamente dígitos decimales.
    if isinstance(timestamp, bool):
        return False

    if isinstance(timestamp, int):
        timestamp_value = timestamp
    elif isinstance(timestamp, str) and re.fullmatch(r"[0-9]+", timestamp):
        timestamp_value = int(timestamp)
    else:
        return False

    # Ventana temporal de ±300 segundos.
    current_time = int(time.time())

    if abs(current_time - timestamp_value) > 300:
        return False

    # Calcular y comparar la firma de forma segura.
    expected_signature = signature(secret, timestamp, body)

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )
