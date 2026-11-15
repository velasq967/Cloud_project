import json
import logging
import sys
from datetime import datetime, timezone

from warehouse_common.correlation import get_correlation_id

_service_name = "service"
_warehouse_id = "-"


class JsonFormatter(logging.Formatter):
    """Formato JSON para poder filtrar logs por correlation_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": _service_name,
            "warehouse_id": _warehouse_id,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    service_name: str,
    level: str = "INFO",
    warehouse_id: str = "-",
) -> None:
    global _service_name, _warehouse_id
    _service_name = service_name
    _warehouse_id = warehouse_id

    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    # Evita duplicar handlers si uvicorn recarga el módulo.
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
