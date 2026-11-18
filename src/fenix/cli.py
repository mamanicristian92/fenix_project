"""CLI de apoyo. Los comandos existen; dependen de completar los TODO del equipo."""
import argparse  # Proporciona subcomandos reproducibles.
import json  # Lee archivos de eventos de prueba.
import os  # Recupera configuración del entorno.
import time  # Obtiene epoch del emisor.
import sys  # Comunica un código de salida al sistema operativo.
from pathlib import Path  # Lee archivos locales elegidos por el operador.
import requests  # Envía un webhook de prueba con bytes firmados.
from dotenv import load_dotenv  # Prepara el entorno de todos los comandos.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.utils.logging_json import setup
from fenix.utils.crypto import signature
from fenix.utils.errors import ProjectError
from fenix.services import sqs, demo, worker, remediation


def main() -> int:
    """Ejecuta un subcomando y cierra el logging antes de devolver el resultado

    Returns:
        0 éxito o interrupción voluntaria; 1 error registrado; argparse usa 2.
    Raises:
        SystemExit: argparse muestra ayuda o rechaza argumentos.
    Side Effects:
        Ejecuta la operación elegida; nunca confirma mensajes desde finally.
    Notes:
        Durante desarrollo, NotImplementedError es como plantilla pendiente.
    """
    load_dotenv()  # No se lee ninguna credencial desde argumentos CLI.
    parser = argparse.ArgumentParser(description="Fénix autorreparación local")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-queues")  # Prepara work y DLQ.
    sub.add_parser("setup-demo")  # Crea el laboratorio autorizado.
    fault = sub.add_parser("fault")  # Introduce una falla controlada.
    fault.add_argument("alias", choices=["node-01", "bucket-01"])
    send = sub.add_parser("send")  # Emite el evento por HTTP.
    send.add_argument("file")  # Archivo JSON visible para la defensa.
    consume = sub.add_parser("worker")  # Procesa la cola local.
    consume.add_argument("--once", action="store_true")
    args = parser.parse_args()  # Errores sintácticos salen con código 2.
    logger, listener = setup("fenix-" + args.command)  # Archivo por proceso.
    code = 0  # El resultado se devuelve fuera de finally.
    try:  # Una frontera de entrada controla errores de las dependencias.
        if args.command == "init-queues":  # Crea primero la DLQ.
            prefix = os.environ["QUEUE_PREFIX"]
            print(sqs.ensure_queues(prefix))  # Las URLs provienen del SDK.

        elif args.command == "setup-demo":  # Crea o recupera recursos.
            print(demo.setup_demo(os.environ["GROUP_ID"]))  # Sin secretos.

        elif args.command == "fault":  # Perturba solo el inventario del grupo.
            demo.inject_fault(args.alias)  # I6 implementa la inyección.

        elif args.command == "send":  # Firma exactamente lo que envía.
            body = Path(args.file).read_bytes()
            payload = json.loads(body)

            if not isinstance(payload, dict):
                raise ProjectError(
                    "El archivo evento debe contener un objeto JSON"
                )
            timestamp = int(time.time())
            secret = os.getenv("WEBHOOK_SECRET")
            if not secret:
                raise ProjectError(
                    "La variable WEBHOOK_SECRET no esta configurada"
                )
            digest = signature(secret, timestamp, body)
            response = requests.post("http://127.0.0.1:8000/webhook", data=body,
                headers={"Content-Type": "application/json",
                         "X-Webhook-Signature": f"t={timestamp},v1={digest}"}, timeout=(2, 15))
            response.raise_for_status()  # No mostrar éxito ante 4xx o 5xx.
            print(response.status_code, response.text)

        elif args.command == "worker":  # Consume un mensaje por consulta.
            prefix = os.environ["QUEUE_PREFIX"]
            worker.run(sqs.queue_url(prefix), remediation.handle, logger, args.once)

    except KeyboardInterrupt:  # Detención manual esperada.
        logger.info("detenido_por_operador")  # No se captura BaseException.

    except (
        ProjectError,
        BotoCoreError,
        OSError,
        ValueError,
        KeyError,
        requests.RequestException,
        NotImplementedError,
    ) as error:

        logger.error(
            "fallo_controlado",
            extra={"status": type(error).__name__},
        )
        print("Revisar configuración o TODO pendiente:", type(error).__name__)
        code = 1  # Un fallo no se presenta como ejecución exitosa.

    finally:  # Se libera el pipeline tanto en éxito como en error.
        listener.stop()  # No return, break ni continue dentro de finally.
    return code  # El código de salida refleja el resultado de la ejecución.


if __name__ == "__main__":  # Permite python -m fenix.cli.
    sys.exit(main())  # Hace visible el resultado a la terminal.
