import hashlib
import hmac
from typing import Union

def signature(
    secret: Union[str, bytes],
    timestamp: Union[int, str],
    body: Union[str, bytes],
) -> str:
    """
    Genera la firma HMAC SHA-256 combinando el timestamp y el cuerpo del webhook.
    
    Esta función implementa una capa de seguridad adicional para proteger 
    el sistema contra ataques de repetición (replay attacks), asegurando
    que la firma dependa tanto del contenido como del momento de emisión.

    Args:
        secret (Union[str, bytes]): Clave secreta compartida (WEBHOOK_SECRET).
        timestamp (Union[int, str]): Marca de tiempo (timestamp) de la petición HTTP.
        body (Union[str, bytes]): Cuerpo o payload del evento recibido.

    Returns:
        str: Firma hexadecimal de 64 caracteres resultante del cálculo HMAC-SHA256.
    """
    # Asegurar que la clave secreta esté en formato de bytes
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
        
    # Asegurar que el cuerpo de la petición esté en formato de bytes
    if isinstance(body, str):
        body = body.encode("utf-8")

    # Concatenar timestamp y body separados por un punto para blindar contra replay attacks
    message = f"{timestamp}.".encode("utf-8") + body
    
    # Retornar el resumen hash hexadecimal calculado con HMAC-SHA256
    return hmac.new(secret, message, hashlib.sha256).hexdigest()
