
import gzip
import json

from fenix.utils.logging_json import setup


def test_rotacion_y_lectura_gzip(tmp_path, monkeypatch):
    # Trabajar en una carpeta temporal para no mezclar logs reales.
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

    # Buscar los archivos comprimidos.
    archivos_gzip = list((tmp_path / "logs").glob("fenix-test.log.*.gz"))

    assert archivos_gzip, "No se generaron archivos GZIP."

    # Comprobar que podemos leer los archivos comprimidos.
    registros = []

    for archivo in archivos_gzip:
        with gzip.open(archivo, "rt", encoding="utf-8") as comprimido:
            for linea in comprimido:
                registros.append(json.loads(linea))

    assert registros, "Los archivos GZIP no contienen registros."
    assert all("message" in registro for registro in registros)
