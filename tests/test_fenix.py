"""Primer contrato de HMAC; integrante 6 agrega el resto de la matriz."""
import pytest  # Verifica la excepción pública de autenticación.
from fenix.utils.crypto import signature, verify
from fenix.utils.errors import ValidationError
import time
from fastapi.testclient import TestClient
from fenix.services import receiver


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
    digest = signature(secret, 1000, body)  # El reloj de la prueba es fijo.
    header = f"t=1000,v1={digest}"  # Mismo formato que el emisor real.
    verify(secret, header, body, now=1000)  # Original debe aceptarse.
    with pytest.raises(ValidationError):  # JSON equivalente no conserva los bytes.
        verify(secret, header, b'{"x": 1}', now=1000)  # Cuerpo modificado.


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