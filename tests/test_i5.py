"""SIMULACION Y CODIGO DE PRUEBA PARA MODULOS worker y remediation  """
import json
import importlib
import sys
import types
import pytest
from fenix.utils.errors import RetryableError
from unittest.mock import Mock


@pytest.fixture
def remediation_module(monkeypatch):

    # 1. Importar configuración real.
    settings = importlib.import_module(
        "fenix.config.settings"
    )

    # 2. Importar módulo de notificaciones.
    notifications = importlib.import_module(
        "fenix.services.notifications"
    )

    # 3. Importar paquete de servicios.
    services = importlib.import_module(
        "fenix.services"
    )

    module_name = "fenix.services.remediation"

    sentinel = object()

    previous_module = sys.modules.pop(module_name, None)

    previous_attr = getattr(
        services, "remediation", sentinel
    )

    if previous_attr is not sentinel:
        delattr(services, "remediation")

    # 4. Bloquear conexiones AWS reales.
    def forbidden_client(service):
        raise AssertionError(
            f"Intento de conexión AWS durante el test: {service}"
        )

    monkeypatch.setattr(
        settings,
        "client",
        forbidden_client,
        raising=False,
    )

    # 5. Proporcionar una notificación ficticia.
    def forbidden_notify(message):
        raise AssertionError(
            "Se intentó utilizar Telegram real durante el test"
        )

    monkeypatch.setattr(
        notifications,
        "notify",
        forbidden_notify,
        raising=False,
    )

    # 6. Importar remediation con las dependencias preparadas.
    module = None

    try:
        module = importlib.import_module(module_name)
        yield module

    finally:
        sys.modules.pop(module_name, None)

        if getattr(services, "remediation", sentinel) is module:
            delattr(services, "remediation")

        if previous_module is not None:
            sys.modules[module_name] = previous_module

        if previous_attr is not sentinel:
            setattr(services, "remediation", previous_attr)


EVENT = {
    "schema_version": 1,
    "event_id": "evt-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-11-12T12:00:00Z",
    "simulate_failures": 0,
}


def test_handle_success(tmp_path, monkeypatch, remediation_module):
    remediation = remediation_module
    # 1. Aislar el entorno de prueba.
    monkeypatch.chdir(tmp_path)

    data = tmp_path / "data"
    data.mkdir()

    # 2. Crear inventario ficticio.
    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-test-001",
        }
    }

    (data / "inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )

    # 3. Preparar simulaciones.
    repair_calls = []
    notify_calls = []

    def fake_repair(resource, event_type):
        repair_calls.append(event_type)
        return "repaired"

    def fake_notify(message):
        notify_calls.append(message)

    monkeypatch.setattr(
        remediation,
        "repair",
        fake_repair,
        raising=False,
    )

    monkeypatch.setattr(
        remediation,
        "notify",
        fake_notify,
    )

    # 4. Ejecutar el handler real.
    remediation.handle(EVENT)

    # 5. Comprobar las operaciones.
    assert len(repair_calls) == 1
    assert len(notify_calls) == 1

    # 6. Comprobar el ledger.
    ledger = json.loads(
        (data / "events.json").read_text(encoding="utf-8")
    )

    record = ledger["evt-001"]

    assert record["attempts"] == 1
    assert record["repair_done"] is True
    assert record["repair_result"] == "repaired"
    assert record["notified"] is True
    assert record["status"] == "completed"


def test_notification_failure_resumes_without_repair(
    tmp_path,
    monkeypatch,
    remediation_module,
):
    remediation = remediation_module

    # 1. Aislar el entorno.
    monkeypatch.chdir(tmp_path)

    data = tmp_path / "data"
    data.mkdir()

    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-test-001",
        }
    }

    (data / "inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )

    # 2. Registrar las llamadas.
    repair_calls = []
    notify_calls = []

    def fake_repair(resource, event_type):
        repair_calls.append(event_type)
        return "repaired"

    def fake_notify(message):
        notify_calls.append(message)

        # Primera notificación falla.
        if len(notify_calls) == 1:
            raise RetryableError("Fallo simulado de Telegram")

    monkeypatch.setattr(
        remediation,
        "repair",
        fake_repair,
        raising=False,
    )

    monkeypatch.setattr(
        remediation,
        "notify",
        fake_notify,
    )

    # 3. Primera ejecución: reparar funciona, notificar falla.
    with pytest.raises(RetryableError):
        remediation.handle(EVENT)

    # 4. Comprobar el estado después del fallo.
    ledger = json.loads(
        (data / "events.json").read_text(encoding="utf-8")
    )

    record = ledger["evt-001"]

    assert record["repair_done"] is True
    assert record["notified"] is False
    assert record["status"] == "notification_pending"

    # 5. Segunda ejecución: debe reintentar solamente el aviso.
    remediation.handle(EVENT)

    # 6. Comprobar que no se repitió la reparación.
    assert len(repair_calls) == 1
    assert len(notify_calls) == 2

    # 7. Verificar el resultado final.
    ledger = json.loads(
        (data / "events.json").read_text(encoding="utf-8")
    )

    record = ledger["evt-001"]

    assert record["attempts"] == 2
    assert record["repair_done"] is True
    assert record["notified"] is True
    assert record["status"] == "completed"


def test_effect_before_ledger_save_failure(
    tmp_path,
    monkeypatch,
    remediation_module,
):
    remediation = remediation_module

    # 1. Aislar el entorno.
    monkeypatch.chdir(tmp_path)

    data = tmp_path / "data"
    data.mkdir()

    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-test-001",
        }
    }

    (data / "inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )

    # 2. Simular el estado externo de AWS.
    cloud_state = {"running": False}
    start_effects = []

    def fake_repair(resource, event_type):
        if not cloud_state["running"]:
            # Simular el efecto externo.
            cloud_state["running"] = True
            start_effects.append("start_instances")
            return "repaired"

        # El recurso ya está en el estado deseado.
        return "already_ok"

    def fake_notify(message):
        return None

    monkeypatch.setattr(
        remediation,
        "repair",
        fake_repair,
        raising=False,
    )

    monkeypatch.setattr(
        remediation,
        "notify",
        fake_notify,
    )

    # 3. Guardar la referencia a la función real.
    real_save = remediation.save
    save_calls = 0

    def fail_after_repair(path, content):
        nonlocal save_calls
        save_calls += 1

        # El primer guardado funciona.
        if save_calls == 1:
            return real_save(path, content)

        # El segundo guardado simula una caída.
        raise OSError("Fallo simulado de escritura")

    monkeypatch.setattr(
        remediation,
        "save",
        fail_after_repair,
    )

    # 4. Ejecutar y provocar el fallo.
    with pytest.raises(OSError):
        remediation.handle(EVENT)

    # 5. El efecto externo ocurrió.
    assert cloud_state["running"] is True
    assert len(start_effects) == 1

    # Pero el ledger todavía no conoce la reparación.
    ledger = json.loads(
        (data / "events.json").read_text(encoding="utf-8")
    )

    record = ledger["evt-001"]

    assert record["repair_done"] is False
    assert record["notified"] is False

    # 6. Restaurar el guardado real.
    monkeypatch.setattr(
        remediation,
        "save",
        real_save,
    )

    # 7. Reanudar el procesamiento.
    remediation.handle(EVENT)

    # 8. El efecto externo no se repitió.
    assert len(start_effects) == 1
    assert cloud_state["running"] is True

    # 9. Comprobar el estado definitivo.
    ledger = json.loads(
        (data / "events.json").read_text(encoding="utf-8")
    )

    record = ledger["evt-001"]

    assert record["attempts"] == 2
    assert record["repair_done"] is True
    assert record["repair_result"] == "already_ok"
    assert record["notified"] is True
    assert record["status"] == "completed"


@pytest.fixture
def worker_module():

    services = importlib.import_module(
        "fenix.services"
    )

    sqs_name = "fenix.services.sqs"
    worker_name = "fenix.services.worker"

    sentinel = object()

    # Preservar importaciones anteriores.
    previous_sqs = sys.modules.pop(sqs_name, None)
    previous_worker = sys.modules.pop(worker_name, None)

    previous_sqs_attr = getattr(services, "sqs", sentinel)
    previous_worker_attr = getattr(services, "worker", sentinel)

    if previous_sqs_attr is not sentinel:
        delattr(services, "sqs")

    if previous_worker_attr is not sentinel:
        delattr(services, "worker")

    # Crear un módulo SQS ficticio.
    fake_sqs = types.ModuleType(sqs_name)

    def unexpected_call(*args, **kwargs):
        raise AssertionError(
            "Se utilizó SQS sin simular la operación en el test"
        )

    fake_sqs.receive = unexpected_call
    fake_sqs.acknowledge = unexpected_call
    fake_sqs.retry_later = unexpected_call

    # Registrar el módulo ficticio antes de importar worker.
    sys.modules[sqs_name] = fake_sqs

    module = None

    try:
        module = importlib.import_module(worker_name)
        yield module

    finally:
        # Limpiar la importación temporal.
        sys.modules.pop(worker_name, None)

        if getattr(services, "worker", sentinel) is module:
            delattr(services, "worker")

        if previous_worker is not None:
            sys.modules[worker_name] = previous_worker

        if previous_worker_attr is not sentinel:
            setattr(services, "worker", previous_worker_attr)

        sys.modules.pop(sqs_name, None)

        if getattr(services, "sqs", sentinel) is fake_sqs:
            delattr(services, "sqs")

        if previous_sqs is not None:
            sys.modules[sqs_name] = previous_sqs

        if previous_sqs_attr is not sentinel:
            setattr(services, "sqs", previous_sqs_attr)


def test_worker_ack_on_success(monkeypatch, worker_module):

    worker = worker_module

    message = {
        "MessageId": "msg-001",
        "ReceiptHandle": "receipt-001",
        "Body": json.dumps(EVENT),
    }

    receive_calls = []
    ack_calls = []
    retry_calls = []
    handler_calls = []

    def fake_receive(url):
        receive_calls.append(url)
        return [message]

    def fake_ack(url, receipt):
        ack_calls.append((url, receipt))

    def fake_retry(url, msg):
        retry_calls.append(msg)
        return 2

    def fake_handler(event):
        handler_calls.append(event)

    monkeypatch.setattr(worker, "receive", fake_receive)
    monkeypatch.setattr(worker, "acknowledge", fake_ack)
    monkeypatch.setattr(worker, "retry_later", fake_retry)

    # Ejecutar una sola consulta a SQS.
    worker.run(
        "queue-test",
        fake_handler,
        Mock(),
        once=True,
    )

    # Comprobar recepción y procesamiento.
    assert receive_calls == ["queue-test"]
    assert handler_calls == [EVENT]

    # Comprobar ACK.
    assert ack_calls == [
        ("queue-test", "receipt-001")
    ]

    # No debe solicitar reintento.
    assert retry_calls == []


def test_worker_no_ack_on_error(monkeypatch, worker_module):

    worker = worker_module

    message = {
        "MessageId": "msg-002",
        "ReceiptHandle": "receipt-002",
        "Body": json.dumps(EVENT),
    }

    ack_calls = []
    retry_calls = []
    handler_calls = []

    def fake_receive(url):
        return [message]

    def fake_ack(url, receipt):
        ack_calls.append(receipt)

    def fake_retry(url, msg):
        retry_calls.append((url, msg))
        return 2

    def fake_handler(event):
        handler_calls.append(event)
        raise RetryableError("Fallo temporal simulado")

    monkeypatch.setattr(worker, "receive", fake_receive)
    monkeypatch.setattr(worker, "acknowledge", fake_ack)
    monkeypatch.setattr(worker, "retry_later", fake_retry)

    worker.run(
        "queue-test",
        fake_handler,
        Mock(),
        once=True,
    )

    # El handler sí fue ejecutado.
    assert handler_calls == [EVENT]

    # No debe existir ACK.
    assert ack_calls == []

    # Debe solicitar un reintento.
    assert len(retry_calls) == 1
    assert retry_calls[0][0] == "queue-test"
    assert retry_calls[0][1] is message
