import time

from fenix.utils.crypto import signature, verify


def test_valid_signature_with_current_timestamp():
    secret = "test-secret"
    body = b'{"event_type":"test"}'
    timestamp = int(time.time())

    sig = signature(secret, timestamp, body)

    assert verify(secret, timestamp, body, sig) is True


def test_rejects_old_timestamp():
    secret = "test-secret"
    body = b'{"event_type":"test"}'
    timestamp = int(time.time()) - 3600

    sig = signature(secret, timestamp, body)

    assert verify(secret, timestamp, body, sig) is False


def test_rejects_future_timestamp():
    secret = "test-secret"
    body = b'{"event_type":"test"}'
    timestamp = int(time.time()) + 3600

    sig = signature(secret, timestamp, body)

    assert verify(secret, timestamp, body, sig) is False


def test_rejects_invalid_timestamp():
    secret = "test-secret"
    body = b'{"event_type":"test"}'
    timestamp = int(time.time())

    sig = signature(secret, timestamp, body)

    assert verify(secret, "abc", body, sig) is False
    assert verify(secret, "123.456", body, sig) is False
