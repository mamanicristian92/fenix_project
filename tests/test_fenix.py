"""Primer contrato de HMAC; integrante 6 agrega el resto de la matriz."""
import pytest  # Verifica la excepción pública de autenticación.
from fenix.utils.crypto import signature, verify
from fenix.utils.errors import ValidationError
import time
from fastapi.testclient import TestClient
from fenix.services import receiver
from fenix.services.events import validate
from fenix.services import remediation
from fenix.utils.errors import RetryableError


# F05 Mismos datos JSON con bytes distintos tras firmar
@pytest.mark.pendiente
def test_signature_authenticates_raw_bytes():
    """Acepta el original y rechaza la misma información con otros bytes.

    Returns:
        None si el verificador respeta el contrato HMAC.
    Raises:
        AssertionError: Si no se rechaza el cuerpo alterado.
        NotImplementedError: Hasta que se implemente el verificador.
    Notes:
        La clave que sigue es solo una fixture pública sin uso fuera del test.
    """
    secret = "clave-ficticia-solo-test"  # No es un secreto de ningún servicio.
    body = b'{"x":1}'  # Espacios distintos producen firmas distintas.
    original_sign = signature(secret, 1000, body)  # El reloj de la prueba es fijo.
    with pytest.raises(ValidationError):  # JSON equivalente no conserva los bytes.
        verify(secret, 1000, b'{"x": 1}', original_sign)  # Cuerpo modificado.

@pytest.mark.pendiente
def test_signature_authenticates_raw_bytes_return_false(monkeypatch):
    """Acepta el original y rechaza la misma información con otros bytes.

    Returns:
        None si el verificador respeta el contrato HMAC.
    Raises:
        AssertionError: Si no se rechaza el cuerpo alterado.
        NotImplementedError: Hasta que se implemente el verificador.
    Notes:
        La clave que sigue es solo una fixture pública sin uso fuera del test.
    """
    secret = "clave-ficticia-solo-test"  # No es un secreto de ningún servicio.
    body = b'{"x":1}'  # Espacios distintos producen firmas distintas.
    original_sign = signature(secret, 1000, body)  # El reloj de la prueba es fijo.

    published = []
    monkeypatch.setattr(
        receiver, "publish",
        lambda *args, **kwargs: published.append(args)
    )
    client = TestClient(receiver.app, raise_server_exceptions=False)
    response = client.post("/webhook", content=b'{"event_id":"evt-001"}')
    assert verify(secret, 1000, b'{"x": 1}', original_sign) == False # Cuerpo modificado.
    assert response.status_code == 401

# F04 Firma ausente/alterada y timestamp de hace una hora
# Firma ausente
@pytest.mark.pendiente
def test_missing_signature_returns_401_without_publishing(monkeypatch):
    """F04: rechaza un webhook sin firma y no publica en SQS."""
    monkeypatch.setenv("WEBHOOK_SECRET", "clave-ficticia-solo-test")
    monkeypatch.setenv("QUEUE_PREFIX", "fenix-grupo01")

    published = []
    monkeypatch.setattr(
        receiver, "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)
    response = client.post("/webhook", content=b'{"event_id":"evt-001"}')

    assert response.status_code == 401
    assert published == []


# Firma alterada
@pytest.mark.pendiente
def test_altered_signature_returns_401_without_publishing(monkeypatch):
    """F04: rechaza una firma modificada y no publica en SQS."""
    secret = "clave-ficticia-solo-test"
    body = b'{"event_id":"evt-001"}'
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)
    altered_digest = ("0" if digest[0] != "0" else "1") + digest[1:]

    monkeypatch.setenv("WEBHOOK_SECRET", secret)
    monkeypatch.setenv("QUEUE_PREFIX", "fenix-grupo01")

    published = []
    monkeypatch.setattr(
        receiver, "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)
    response = client.post(
        "/webhook",
        content=body,
        headers={"X-Webhook-Signature": f"t={timestamp},v1={altered_digest}"},
    )

    assert response.status_code == 401
    assert published == []


# Firma con timestamp de hace una hora
@pytest.mark.pendiente
def test_old_timestamp_returns_401_without_publishing(monkeypatch):
    """F04: rechaza una firma válida cuyo timestamp tiene una hora."""
    secret = "clave-ficticia-solo-test"
    body = b'{"event_id":"evt-001"}'
    old_timestamp = int(time.time()) - 3600
    digest = signature(secret, old_timestamp, body)

    monkeypatch.setenv("WEBHOOK_SECRET", secret)
    monkeypatch.setenv("QUEUE_PREFIX", "fenix-grupo01")

    published = []
    monkeypatch.setattr(
        receiver, "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Webhook-Signature": f"t={old_timestamp},v1={digest}"
        },
    )

    assert response.status_code == 401
    assert published == []


# F06 JSON roto firmado; luego lista JSON firmada
# Json roto firmado
@pytest.mark.pendiente
def test_malformed_json_returns_400_without_publishing(monkeypatch):
    secret = "clave-ficticia-solo-test"
    body = b'{"event_id": "evt-001"'  # JSON incompleto.
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)

    monkeypatch.setenv("WEBHOOK_SECRET", secret)

    published = []
    monkeypatch.setattr(
        receiver,
        "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)

    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Webhook-Signature": f"t={timestamp},v1={digest}"
        }
    )

    assert response.status_code == 400
    assert published == []


# Lista de JSON firmada
@pytest.mark.pendiente
def test_json_list_returns_422_without_publishing(monkeypatch):
    secret = "clave-ficticia-solo-test"
    body = b'[{"event_id": "evt-001"}]'
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)

    monkeypatch.setenv("WEBHOOK_SECRET", secret)

    # Evitamos depender del inventario real.
    monkeypatch.setattr(receiver, "load", lambda path: {})

    published = []
    monkeypatch.setattr(
        receiver,
        "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)

    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Webhook-Signature": f"t={timestamp},v1={digest}"
        }
    )

    assert response.status_code == 422
    assert published == []

# F07 Alias ajeno y claves extra
# Alias ajeno
@pytest.mark.pendiente
def test_event_with_unknown_resource_alias_is_rejected():
    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-0123456789abcdef0",
            "expected_tags": {}
        }
    }

    event = {
        "schema_version": 1,
        "event_id": "evt-001",
        "event_type": "instance.stopped",
        "resource_id": "node-99",
        "occurred_at": "2026-11-18T12:00:00Z",
        "simulate_failures": 0
    }

    with pytest.raises(ValidationError):
        validate(event, inventory)


# claves extra
@pytest.mark.pendiente
def test_event_with_additional_field_is_rejected():
    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-0123456789abcdef0",
            "expected_tags": {}
        }
    }

    event = {
        "schema_version": 1,
        "event_id": "evt-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01",
        "occurred_at": "2026-11-18T12:00:00Z",
        "simulate_failures": 0,
        "admin": True   # clave extra
    }

    with pytest.raises(ValidationError):
        validate(event, inventory)


# F08 en pruebas de integración


# F09 simulate_failures=2, ID nuevo
def test_transient_failures_are_retried_before_repair(monkeypatch):
    """Reintenta los fallos simulados antes de reparar y notificar."""
    inventory = {
        "node-01": {
            "type": "ec2",
            "id": "i-0123456789abcdef0",
            "expected_tags": {}
        }
    }
    event = {
        "schema_version": 1,
        "event_id": "evt-retry-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01",
        "occurred_at": "2026-11-18T12:00:00Z",
        "simulate_failures": 2
    }

    ledger = {}
    calls = []

    # Aísla la lectura del inventario y del ledger.
    def fake_load(path):
        if str(path).endswith("inventory.json"):
            return inventory
        if str(path).endswith("events.json"):
            return ledger
        raise AssertionError(f"Ruta inesperada: {path}")

    # Conserva en memoria lo que handle() guarda en el ledger.
    def fake_save(path, data):
        ledger.update(data)

    monkeypatch.setattr(remediation, "load", fake_load)
    monkeypatch.setattr(remediation, "save", fake_save)

    # Aísla la validación del evento: este test se concentra en los reintentos.
    monkeypatch.setattr(
        remediation, "validate", lambda event, inventory: event
    )

    monkeypatch.setattr(
        remediation,
        "repair",
        lambda *args, **kwargs: calls.append("repair") or "repaired"
    )
    monkeypatch.setattr(
        remediation,
        "notify",
        lambda *args, **kwargs: calls.append("notify")
    )

    print("ledger: ")
    print(ledger)
    # Los dos primeros intentos deben fallar de forma transitoria.
    with pytest.raises(RetryableError):
        remediation.handle(event)

    assert ledger["evt-retry-001"]["attempts"] == 1
    assert calls == []

    with pytest.raises(RetryableError):
        remediation.handle(event)

    assert ledger["evt-retry-001"]["attempts"] == 2
    assert calls == []

    # El tercer intento supera los fallos simulados.
    remediation.handle(event)

    assert ledger["evt-retry-001"]["attempts"] == 3
    assert calls == ["repair", "notify"]
