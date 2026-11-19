import logging

from psycopg2.extras import Json
from shared.db import get_connection
from shared.logging import configure_worker_logging
from shared.rabbit import consume, queue_name

configure_worker_logging("audit-worker")
logger = logging.getLogger("worker.audit")

CONSUMER = "audit-worker"
QUEUE = queue_name("audit.events")


def handle(event: dict) -> None:
    event_id = event.get("event_id")
    event_type = event.get("event_type")
    payload = event.get("payload") or {}
    warehouse_id = payload.get("warehouse_id") or event.get("source")
    correlation_id = event.get("correlation_id")
    occurred_at = event.get("occurred_at")

    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_log (
                    event_id, consumer, event_type, warehouse_id,
                    correlation_id, payload, occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id, consumer) DO NOTHING
                """,
                (
                    event_id,
                    CONSUMER,
                    event_type,
                    warehouse_id,
                    correlation_id,
                    Json(payload),
                    occurred_at,
                ),
            )
        logger.info(
            "audit_event_stored event_id=%s event_type=%s", event_id, event_type
        )
    finally:
        connection.close()


if __name__ == "__main__":
    consume(QUEUE, handle)
