# F04	Firma ausente/alterada y timestamp de hace una hora	401 y ningún mensaje nuevo
# F05	Mismos datos JSON con bytes distintos tras firmar	401 por HMAC inválida
# F06	JSON roto firmado; luego lista JSON firmada	400 y 422 respectivamente; sin publicación
# F07	Alias ajeno y claves extra	Rechazo de esquema; ningún cambio cloud
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
# Cambiamos el contrato de la función verify():
# No levanta ValidationError, devuelve False

def test_signature_authenticates_raw_bytes():
    """
    Acepta el original y rechaza la misma información con otros bytes.

    Returns:
        None si el verificador respeta el contrato HMAC.
    Raises:
        AssertionError: Si no se rechaza el cuerpo alterado.

    Notes:
        La clave que sigue es sólo una fixture pública sin uso fuera del test.
    """

    secret = "clave-ficticia-solo-test"
    body = b'{"x":1}'
    # usamos un timestamp es estatico
    original_sign = signature(secret, 1000, body)

    assert verify(secret, 1000, body, original_sign) is True
    assert verify(secret, 1000, b'{"x": 1}', original_sign) is False


# F04 Firma ausente/alterada y timestamp de hace una hora
# Firma ausente => codigo esperado 401

@pytest.mark.pendiente
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


# F04
# Firma con timestamp de hace una hora
# codigo esperado 401
@pytest.mark.pendiente
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
    """
    Verifica el rechazo de solicitudes con cuerpos JSON malformados.

    Firma el cuerpo de la solicitud para superar la autenticación HMAC
    y envía un documento JSON incompleto. Comprueba que el receptor
    identifique el error de sintaxis y no publique el evento en SQS.

    Args:
        monkeypatch: Permite sustituir la publicación en SQS
            para verificar que no se produzcan envíos.
    Returns:
        None si el JSON malformado produce una respuesta HTTP 400
        y no se publica ningún mensaje.
    Raises:
        AssertionError: Si el receptor no rechaza el cuerpo inválido
            o intenta publicarlo.
    """

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
    """
    Verifica el rechazo de documentos JSON cuyo elemento raíz es una lista.

    Firma un cuerpo JSON sintácticamente válido que contiene una lista
    en lugar de un objeto. Comprueba que el receptor rechace una
    estructura incompatible con el formato esperado y no publique
    el evento en SQS.

    Args:
        monkeypatch: Permite sustituir la publicación en SQS
            para verificar que no se produzcan envíos.
    Returns:
        None si la estructura JSON es rechazada con HTTP 422
        y no se publica ningún mensaje.
    Raises:
        AssertionError: Si el receptor acepta la estructura incorrecta
            o intenta publicarla.
    """

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
def test_event_with_unknown_resource_alias_is_rejected():
    """
    Verifica que los eventos referencien recursos existentes en el inventario.

    Construye un inventario con un recurso EC2 conocido y un evento
    que referencia un alias inexistente. Comprueba que la validación
    impida procesar eventos asociados a recursos no registrados.

    Returns:
        None si la validación rechaza el alias desconocido.
    Raises:
        ValidationError: Si el recurso indicado no pertenece
            al inventario.
        AssertionError: Si el evento es aceptado sin corresponder
            a un recurso registrado.
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
        "event_id": "evt-001",
        "event_type": "instance.stopped",
        "resource_id": "node-99",
        "occurred_at": "2026-11-18T12:00:00Z",
        "simulate_failures": 0
    }

    with pytest.raises(ValidationError):
        validate(event, inventory)


# claves extra
def test_event_with_additional_field_is_rejected():
    """
    Verifica que el esquema de eventos no admita campos adicionales.

    Construye un evento válido en sus campos obligatorios, pero incorpora
    una propiedad no contemplada en el contrato. Comprueba que la
    validación rechace estructuras que excedan el esquema definido.

    Returns:
        None si el evento con propiedades adicionales es rechazado.
    Raises:
        ValidationError: Si el evento contiene campos no permitidos.
        AssertionError: Si la validación acepta el campo adicional.
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
    """
    Verifica que los fallos transitorios se reintenten antes de reparar.

    Simula un evento con dos fallos transitorios y controla las
    dependencias externas mediante monkeypatch. Comprueba que los
    dos primeros intentos generen RetryableError y que la reparación
    y notificación se ejecuten únicamente en el tercer intento.

    Args:
        monkeypatch: Permite aislar la lectura y escritura del inventario
            y del ledger, así como sustituir la validación, reparación
            y notificación por implementaciones controladas.
    Returns:
        None si se registran tres intentos y la reparación y notificación
        se ejecutan una única vez, después de superar los fallos.
    Raises:
        RetryableError: Durante los dos primeros intentos simulados.
        AssertionError: Si los intentos no se contabilizan correctamente
            o las operaciones de reparación y notificación se ejecutan
            antes de superar los fallos transitorios.
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
    assert calls == []      # nose llamaron a repair() ni a notify()

    with pytest.raises(RetryableError):
        remediation.handle(event)

    assert ledger["evt-retry-001"]["attempts"] == 2
    assert calls == []

    # El tercer intento supera los fallos simulados.
    remediation.handle(event)

    assert ledger["evt-retry-001"]["attempts"] == 3
    assert calls == ["repair", "notify"]
