
"""Logging estructurado JSONL con cola, rotación y compresión GZIP."""

import gzip
import json
import logging
import os
import queue
import shutil

from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
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
            data[field] = getattr(record, field, None)

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False)


def gzip_name(name: str) -> str:
    """Agrega la extensión GZIP al archivo rotado."""
    return name + ".gz"


def gzip_rotate(source: str, dest: str) -> None:
    """Comprime el archivo rotado y elimina el original."""
    with open(source, "rb") as origin, gzip.open(dest, "wb") as target:
        shutil.copyfileobj(origin, target)

    os.remove(source)


def setup(
    name: str,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
) -> tuple[logging.Logger, QueueListener]:
    """Configura logging JSONL con cola, rotación y compresión GZIP."""
    Path("logs").mkdir(parents=True, exist_ok=True)

    sink = RotatingFileHandler(
        f"logs/{name}.jsonl",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )

    sink.setFormatter(JSONFormatter())
    sink.namer = gzip_name
    sink.rotator = gzip_rotate

    records = queue.Queue()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logger.propagate = False
    logger.addHandler(QueueHandler(records))

    listener = QueueListener(
        records,
        sink,
        respect_handler_level=True,
    )

    listener.start()
    return logger, listener
