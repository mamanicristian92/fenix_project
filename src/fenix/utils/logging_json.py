
"""Logging estructurado JSON con cola, rotación y compresión GZIP."""

import gzip
import json
import logging
import os
import queue
import shutil

from datetime import datetime, timezone
from logging.handlers import (
    QueueHandler,
    QueueListener,
    RotatingFileHandler,
)
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Convierte cada registro en una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Transforma un registro de logging en texto JSON."""

        data = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.threadName,
        }

        optional_fields = (
            "event_id",
            "message_id",
            "resource_id",
            "attempt",
            "action",
            "status",
        )

        for field in optional_fields:
            value = getattr(record, field, None)
            if value is not None:
                data[field] = value

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False)
def gzip_namer(default_name: str) -> str:
    """Agrega la extensión .gz al nombre del archivo rotado."""
    return default_name + ".gz"
def gzip_rotator(source: str, dest: str) -> None:
    """Comprime un archivo rotado y elimina el original."""

    with open(source, "rb") as archivo_origen:
        with gzip.open(dest, "wb") as archivo_comprimido:
            shutil.copyfileobj(archivo_origen, archivo_comprimido)

    os.remove(source)
def setup(
    name: str,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
) -> tuple[logging.Logger, QueueListener]:
    """Configura el logging JSON con cola, rotación y compresión GZIP."""

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.namer = gzip_namer
    file_handler.rotator = gzip_rotator
    log_queue = queue.Queue()
    queue_handler = QueueHandler(log_queue)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(queue_handler)
    listener = QueueListener(
        log_queue,
        file_handler,
        respect_handler_level=True,
    )
    listener.start()
    return logger, listener
