
import gzip
import json

from fenix.utils.logging_json import setup


def test_rotacion_y_lectura_gzip(tmp_path, monkeypatch):
    # Trabajar en una carpeta temporal.
    monkeypatch.chdir(tmp_path)

    logger, listener = setup(
        "fenix-test",
        max_bytes=200,
        backup_count=3,
    )

    try:
        # Generar eventos suficientes para forzar la rotación.
        for numero in range(20):
            logger.info(
                "Evento de prueba numero %s",
                numero,
                extra={"event_id": str(numero)},
            )
    finally:
        # Detener el listener y cerrar el archivo.
        listener.stop()
        for handler in listener.handlers:
            handler.close()

    # Buscar los archivos GZIP del proceso actual.
    archivos_gzip = list(
        (tmp_path / "logs").glob("fenix-test-*.jsonl.*.gz")
    )

    assert archivos_gzip, "No se generaron archivos GZIP."

    registros = []

    for archivo in archivos_gzip:
        with gzip.open(archivo, "rt", encoding="utf-8") as comprimido:
            for linea in comprimido:
                registros.append(json.loads(linea))

    assert registros, "Los archivos GZIP no contienen registros."

    campos_obligatorios = {
        "timestamp",
        "level",
        "logger",
        "message",
        "process",
        "thread",
        "event_id",
        "message_id",
        "resource_id",
        "attempt",
        "action",
        "status",
    }

    for registro in registros:
        assert campos_obligatorios.issubset(registro.keys())
        assert registro["level"] == "INFO"
        assert registro["logger"] == "fenix-test"
        assert registro["event_id"] is not None
