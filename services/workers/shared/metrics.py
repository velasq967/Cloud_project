import os

from prometheus_client import Counter, Histogram, start_http_server

MESSAGES_PROCESSED = Counter(
    "warehouse_worker_messages_total",
    "Mensajes procesados por cola y resultado",
    ["queue", "status"],
)

MESSAGE_DURATION = Histogram(
    "warehouse_worker_message_duration_seconds",
    "Duración del procesamiento de un mensaje",
    ["queue"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

RETRIES = Counter(
    "warehouse_worker_retries_total",
    "Reintentos de mensajes",
    ["queue"],
)

DLQ_MESSAGES = Counter(
    "warehouse_worker_dlq_total",
    "Mensajes enviados a DLQ",
    ["queue"],
)

OUTBOX_PUBLISHED = Counter(
    "warehouse_worker_outbox_published_total",
    "Eventos de outbox publicados",
    ["warehouse_id"],
)


def start_metrics_server() -> None:
    """Expone /metrics del worker en PROMETHEUS_PORT (9100 por defecto)."""
    port = int(os.getenv("PROMETHEUS_PORT", "9100"))
    try:
        start_http_server(port)
    except OSError:
        # Si dos procesos comparten red/namespace, no tumbar el worker.
        pass
