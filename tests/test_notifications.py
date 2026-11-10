
from types import SimpleNamespace

import pytest

from fenix.services import notifications
from fenix.utils.errors import PermanentError, RetryableError


def respuesta(status_code=200, data=None, headers=None):
    return SimpleNamespace(
        status_code=status_code,
        headers=headers or {},
        json=lambda: data if data is not None else {"ok": True},
    )


def configurar_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token_de_prueba")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")


def test_notify_correctamente(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(url, json, timeout):
        assert "token_de_prueba" in url
        assert json["chat_id"] == "123456"
        assert json["text"] == "Prueba Fenix"
        assert timeout == (2, 5)
        return respuesta()

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    assert notifications.notify("Prueba Fenix") is None


def test_faltan_credenciales(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(PermanentError):
        notifications.notify("Prueba")


def test_mensaje_vacio(monkeypatch):
    configurar_telegram(monkeypatch)

    with pytest.raises(PermanentError):
        notifications.notify("   ")


def test_error_de_conexion(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(*args, **kwargs):
        raise notifications.requests.ConnectionError()

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    with pytest.raises(RetryableError):
        notifications.notify("Prueba")


def test_error_429(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(*args, **kwargs):
        return respuesta(
            status_code=429,
            headers={"Retry-After": "60"},
        )

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    with pytest.raises(RetryableError) as error:
        notifications.notify("Prueba")

    assert error.value.retry_after == 30


def test_error_500(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(*args, **kwargs):
        return respuesta(status_code=500)

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    with pytest.raises(RetryableError):
        notifications.notify("Prueba")


def test_error_400(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(*args, **kwargs):
        return respuesta(status_code=400)

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    with pytest.raises(PermanentError):
        notifications.notify("Prueba")


def test_telegram_rechaza_mensaje(monkeypatch):
    configurar_telegram(monkeypatch)

    def post_falso(*args, **kwargs):
        return respuesta(data={"ok": False})

    monkeypatch.setattr(notifications.requests, "post", post_falso)

    with pytest.raises(PermanentError):
        notifications.notify("Prueba")
