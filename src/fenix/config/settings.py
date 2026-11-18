"""Configuración de apoyo entregada; no guarda credenciales en el código."""
import os  
from urllib.parse import urlparse  
import boto3  
from botocore.config import Config  
from dotenv import load_dotenv  
from fenix.utils.errors import ValidationError  


def client(service: str):
    """Construye un cliente dirigido exclusivamente al emulador local.

    Args:
        service: Nombre del servicio; sqs, s3 o ec2.
    Returns:
        Cliente Boto3 del servicio solicitado.
    Raises:
        ValidationError: Si falta una variable o el destino no es loopback.
        BotoCoreError: Si Boto3 no puede construir el cliente.
    Notes:
        Python corre en el host. No se usan perfiles ni credenciales de AWS real.
        El tiempo de lectura supera el long polling de diez segundos.
    """
    load_dotenv()  
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")  
    try:  
        parsed = urlparse(endpoint)  
        port = parsed.port  
    except ValueError as error:  
        raise ValidationError("Endpoint local inválido") from error
    if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1")
            or port != 4566 or parsed.username or parsed.password):
        raise ValidationError("Usar http://localhost:4566 en este TP")  
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
        if not os.environ.get(key):  
            raise ValidationError(f"Falta variable {key}")  
    return boto3.client(  
        service, endpoint_url=endpoint,
        region_name=os.environ["AWS_DEFAULT_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(connect_timeout=2, read_timeout=15,
                      retries={"mode": "standard", "total_max_attempts": 2},
                      s3={"addressing_style": "path"}),
    )  
