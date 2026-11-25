"""Publica los eventos pendientes del outbox de una bodega (fase 10)."""

import logging
import time

from psycopg2.extras import RealDictCursor
from shared.config import settings
from shared.db import get_connection
from shared.logging import configure_worker_logging
from shared.metrics import OUTBOX_PUBLISHED, start_metrics_server
from shared.rabbit import publish_event

configure_worker_logging("outbox-worker")
logger = logging.getLogger("worker.outbox")

POLL_SECONDS = 1
BATCH_SIZE = 50


def publish_pending() -> int:
    connection = get_connection()
    published = 0
    try:
        with connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, event_id, event_type, routing_key, correlation_id, payload
                FROM outbox_events
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (BATCH_SIZE,),
            )
            rows = cursor.fetchall()

            for row in rows:
                try:
                    publish_event(row["payload"], row["routing_key"])
                    cursor.execute(
                        """
                        UPDATE outbox_events
                        SET published_at = NOW(), attempts = attempts + 1,
                            last_error = NULL
                        WHERE id = %s
                        """,
                        (row["id"],),
                    )
                    OUTBOX_PUBLISHED.labels(warehouse_id=settings.WAREHOUSE_ID).inc()
                    published += 1
                except Exception as exc:
                    cursor.execute(
                        """
                        UPDATE outbox_events
                        SET attempts = attempts + 1, last_error = %s
                        WHERE id = %s
                        """,
                        (str(exc)[:500], row["id"]),
                    )
                    logger.warning(
                        "outbox_publish_failed event_id=%s error=%s",
                        row["event_id"],
                        exc,
                    )
    finally:
        connection.close()
    return published


def run() -> None:
    start_metrics_server()
    logger.info(
        "outbox_worker_started warehouse=%s poll_seconds=%s",
        settings.WAREHOUSE_ID,
        POLL_SECONDS,
    )
    while True:
        try:
            published = publish_pending()
            if published:
                logger.info("outbox_batch_published count=%s", published)
        except Exception:
            logger.exception("outbox_worker_error")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
