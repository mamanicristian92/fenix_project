"""Guía ejecutable del integrante 6; sustituir cada pendiente por aserciones reales."""
# PYTHONPATH=src python -m pytest -v tests/test_scenarios.py -k duplicate
import pytest  # Mantiene visibles los casos sin implementar.
import copy
from fenix.services import remediation, worker
import json
import logging
from fenix.utils.errors import RetryableError
import time
import uuid
from fenix.config.settings import client
from fenix.services.sqs import ensure_queues


def test_duplicate_is_idempotent(monkeypatch):
    """Comprueba que repetir un evento no repite recursos ni acciones completadas.

    Returns:
        None cuando dos ejecuciones conservan el estado final esperado.
    Raises:
        NotImplementedError: Hasta que I6 implemente la preparación y aserciones.
    Notes:
        Usar un cliente falso con contador de llamadas; reinicializar el handler
        leyendo el mismo ledger para que el ensayo represente un reinicio.
    """

    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-0123456789abcdef0",
            "expected_tags": {}
        }
    }

    event = {
        "schema_version": 1,
        "event_id": "evt-duplicate-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01",
        "occurred_at": "2026-11-19T12:00:00Z",
        "simulate_failures": 0
    }

    # Simula el almacenamiento persistente del ledger.
    storage = {}
    calls = []

    def fake_load(path):
        if str(path).endswith("inventory.json"):
            return inventory
        if str(path).endswith("events.json"):
            return copy.deepcopy(storage)
        raise AssertionError(f"Ruta inesperada: {path}")

    def fake_save(path, data):
        storage.clear()
        storage.update(copy.deepcopy(data))

    monkeypatch.setattr(remediation, "load", fake_load)
    monkeypatch.setattr(remediation, "save", fake_save)
    monkeypatch.setattr(
        remediation, "validate",
        lambda event, inventory: event
    )
    monkeypatch.setattr(
        remediation, "repair",
        lambda *args, **kwargs: calls.append("repair") or "repaired"
    )
    monkeypatch.setattr(
        remediation, "notify",
        lambda *args, **kwargs: calls.append("notify")
    )

    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    # Primera ejecución: repara y notifica.
    remediation.handle(event)

    assert calls == ["repair", "notify"]
    assert storage["evt-duplicate-001"]["status"] == "completed"

    # Segunda ejecución: reconoce el evento completado.
    remediation.handle(event)

    assert calls == ["repair", "notify"]
    assert storage["evt-duplicate-001"]["status"] == "completed"
    assert storage["evt-duplicate-001"]["attempts"] == 2


def test_ack_is_after_success(monkeypatch):
    """Verifica que un handler fallido jamás confirma la entrega de SQS.

    Returns:
        None si fallo=retry sin ACK y éxito=ACK exactamente al finalizar.
    Raises:
        NotImplementedError: Hasta que I6 conecte fixtures y mocks del transporte.
    Notes:
        No reemplazar el worker entero por un mock: observar llamadas reales de run.
    """

    """Verifica que el worker confirme el mensaje solamente tras el éxito."""

    event = {
        "event_id": "evt-ack-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01"
    }

    message = {
        "MessageId": "msg-001",
        "ReceiptHandle": "receipt-001",
        "Body": json.dumps(event),
        "Attributes": {
            "ApproximateReceiveCount": "1"
        }
    }

    calls = []

    monkeypatch.setattr(
        worker, "receive",
        lambda url: [message]
    )

    monkeypatch.setattr(
        worker, "retry_later",
        lambda url, message: calls.append("retry") or 2
    )

    monkeypatch.setattr(
        worker, "acknowledge",
        lambda url, receipt: calls.append("ack")
    )

    logger = logging.getLogger("test_worker")

    # Caso 1: el handler falla.
    def failing_handler(event):
        calls.append("handler")
        raise RetryableError("Fallo temporal")

    worker.run("test-queue", failing_handler, logger, once=True)

    assert calls == ["handler", "retry"]

    # Caso 2: el handler termina correctamente.
    calls.clear()

    def successful_handler(event):
        calls.append("handler")

    worker.run("test-queue", successful_handler, logger, once=True)

    assert calls == ["handler", "ack"]


# F10 Falla persistente, ID nuevo
@pytest.mark.integracion
def test_redrive_with_localstack():
    """Comprueba DLQ efectiva usando el broker, no una lista simulada en Python.

    Returns:
        None si un mensaje venenoso termina en la DLQ y el worker sigue vivo.
    Raises:
        NotImplementedError: Hasta implementar el ensayo con espera total acotada.
    Side Effects:
        Crea colas de prueba exclusivas y las limpia después de guardar evidencia.
    Notes:
        Usar un prefijo de test nuevo y no purgar colas del laboratorio del grupo.
    """

    prefix = f"efimero-grupo01-i6d-{uuid.uuid4().hex[:8]}"
    sqs = client("sqs")

    work_url = None
    dead_url = None

    poison_body = '{"event_id": "evt-poison-001"'

    try:
        # Crear colas exclusivas con RedrivePolicy.
        work_url, dead_url = ensure_queues(prefix)

        # Publicar un JSON malformado directamente en SQS.
        sqs.send_message(
            QueueUrl=work_url,
            MessageBody=poison_body
        )

        logger = logging.getLogger("test_redrive")

        def handler(event):
            raise AssertionError(
                "El handler no debería recibir un JSON malformado"
            )

        deadline = time.monotonic() + 120

        while time.monotonic() < deadline:

            # Ejecutar una consulta y un procesamiento del worker.
            worker.run(
                work_url,
                handler,
                logger,
                once=True
            )

            # Consultar si el mensaje llegó a la DLQ.
            response = sqs.receive_message(
                QueueUrl=dead_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1
            )

            messages = response.get("Messages", [])

            if messages:
                message = messages[0]

                assert message["Body"] == poison_body

                # Eliminar el mensaje de prueba de la DLQ.
                sqs.delete_message(
                    QueueUrl=dead_url,
                    ReceiptHandle=message["ReceiptHandle"]
                )

                return

        raise AssertionError(
            "El mensaje venenoso no llegó a la DLQ en 120 segundos"
        )

    finally:
        # Eliminar exclusivamente las colas creadas por este test.
        if work_url:
            sqs.delete_queue(QueueUrl=work_url)

        if dead_url:
            sqs.delete_queue(QueueUrl=dead_url)
