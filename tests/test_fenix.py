"""Primer contrato de HMAC; integrante 6 agrega el resto de la matriz."""
# F04	Firma ausente/alterada y timestamp de hace una hora	401 y ningún mensaje nuevo
# F05	Mismos datos JSON con bytes distintos tras firmar	401 por HMAC inválida
# F06	JSON roto firmado; luego lista JSON firmada	400 y 422 respectivamente; sin publicación
# F07	Alias ajeno y claves extra	Rechazo de esquema; ningún cambio cloud
# 
# F09	simulate_failures=2, ID nuevo	Backoff 2 y 4; después reparación y ACK

import pytest  # Verifica la excepción pública de autenticación.
from fenix.utils.crypto import signature, verify
from fenix.utils.errors import ValidationError
import time
from fastapi.testclient import TestClient
from fenix.services import receiver
from fenix.services.events import validate
from fenix.services import remediation
from fenix.utils.errors import RetryableError
import os
from dotenv import load_dotenv

load_dotenv()

secret = os.getenv("WEBHOOK_SECRET", "")


# F05 Mismos datos JSON con bytes distintos tras firmar

def test_signature_authenticates_raw_bytes():
    """Acepta el original y rechaza la misma información con otros bytes.

    Returns:
        None si el verificador respeta el contrato HMAC.
    Raises:
        AssertionError: Si no se rechaza el cuerpo alterado.

    Notes:
        La clave que sigue es sólo una fixture pública sin uso fuera del test.
    """

    secret = "clave-ficticia-solo-test"
    body = b'{"x":1}'
    original_sign = signature(secret, 1000, body)

    assert verify(secret, 1000, body, original_sign) is True
    assert verify(secret, 1000, b'{"x": 1}', original_sign) is False


# F04 Firma ausente/alterada y timestamp de hace una hora
# Firma ausente => codigo esperado 401

def test_missing_signature_returns_401_without_publishing(monkeypatch):
    """
    Verifica el rechazo de webhooks que no incluyen firma.
    Envía una solicitud al endpoint sin el encabezado
    X-Webhook-Signature y comprueba que sea rechazada sin publicar
    ningún mensaje en la cola SQS.

    Args:
        monkeypatch: Permite sustituir la publicación en SQS
            para verificar que no se produzcan envíos.
    Returns:
        None si la solicitud es rechazada y no se publica ningún mensaje.
    Raises:
        AssertionError: Si el endpoint acepta la solicitud o intenta
            publicar un mensaje sin firma.
    """

    published = []

    monkeypatch.setattr(
        receiver, "publish",
        lambda *args, **kwargs: published.append(args)
    )

    client = TestClient(receiver.app, raise_server_exceptions=False)
    response = client.post("/webhook", content=b'{"event_id":"evt-001"}')

    assert response.status_code == 401
    assert published == []


# F04
# Firma alterada => codigo esperado 401

def test_altered_signature_returns_401_without_publishing(monkeypatch):
    """
    Verifica el rechazo de webhooks con firmas HMAC alteradas.
    Genera una firma válida para el cuerpo de la solicitud y modifica
    su digest antes de enviarla al endpoint. Comprueba que el receptor
    rechace la autenticación y no publique el evento en SQS.

    Args:
        monkeypatch: Permite sustituir la publicación en SQS
            para verificar que no se produzcan envíos.

    Returns:
        None si la firma modificada es rechazada y no se publica
        ningún mensaje.

    Raises:
        AssertionError: Si el receptor acepta la firma alterada
            o publica el evento.
    """
    body = b'{"event_id":"evt-001"}'
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)
    altered_digest = ("0" if digest[0] != "0" else "1") + digest[1:]

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

def test_old_timestamp_returns_401_without_publishing(monkeypatch):
    """
    Verifica el rechazo de firmas con timestamps fuera de tolerancia.

    Genera una firma HMAC válida utilizando un timestamp de una hora
    anterior al momento de la solicitud. Comprueba que el receptor
    rechace el webhook por antigüedad y no publique el evento en SQS.

    Args:
        monkeypatch: secretPermite sustituir la publicación en SQS
            para verificar que no se produzcan envíos.
    Returns:
        None si el webhook antiguo es rechazado y no se publica
        ningún mensaje.
    Raises:
        AssertionError: Si el receptor acepta un timestamp fuera
            de la tolerancia permitida o publica el evento.
    """

    body = b'{"event_id":"evt-001"}'
    old_timestamp = int(time.time()) - 3600
    digest = signature(secret, old_timestamp, body)

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
# Json roto firmado => codigo esperado 400 sin publicación

def test_malformed_json_returns_400_without_publishing(monkeypatch):
    
    body = b'{"event_id": "evt-001"'  # JSON incompleto.
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)

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


# Lista de JSON firmada => codigo esperado 422 sin publicación
@pytest.mark.pendiente
def test_json_list_returns_422_without_publishing(monkeypatch):
    
    body = b'[{"event_id": "evt-001"}]'
    timestamp = int(time.time())
    digest = signature(secret, timestamp, body)

    # Evitamos depender del inventario real.
    # monkeypatch.setattr(receiver, "load", lambda path: {})

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


# F07 Alias ajeno y claves extra // Pruebas sobre utils/validation.py
# Alias ajeno => Raise esperado: ValidationError
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


# F09 simulate_failures=2, ID nuevo // Pruebas sobre services/remediation.py
# Backoff 2 y 4; después reparación y ACK
# => Resultado esperado ledger["evt-retry-001"]["attempts"] == 3 &
# Una llamada a repair() y notify()
# Una excepción levantada por cada intento
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
