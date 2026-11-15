import logging
from datetime import datetime, timezone

from psycopg2.extras import Json
from shared.config import settings
from shared.db import get_connection, get_cursor
from shared.logging import configure_worker_logging
from shared.rabbit import consume

configure_worker_logging("report-worker")
logger = logging.getLogger("worker.report")

QUEUE = "report.jobs.q"
CONSUMER = "report-worker"


def build_inventory_snapshot(connection, warehouse_id: str) -> dict:
    with get_cursor(connection) as cursor:
        cursor.execute(
            """
            SELECT p.id, p.sku, p.name, p.category, p.unit,
                   i.quantity, i.reserved_quantity,
                   (i.quantity - i.reserved_quantity) AS available_quantity
            FROM products p
            LEFT JOIN inventory i
              ON i.product_id = p.id AND i.warehouse_id = %s
            ORDER BY p.id
            """,
            (warehouse_id,),
        )
        rows = cursor.fetchall()

    items = [dict(row) for row in rows]
    return {
        "warehouse_id": warehouse_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "INVENTORY_SNAPSHOT",
        "items": items,
        "totals": {
            "products": len(items),
            "quantity": sum(item.get("quantity") or 0 for item in items),
            "reserved": sum(item.get("reserved_quantity") or 0 for item in items),
        },
    }


def build_movements_export(connection, warehouse_id: str, limit: int = 500) -> dict:
    with get_cursor(connection) as cursor:
        cursor.execute(
            """
            SELECT id, product_id, type, quantity, reference,
                   correlation_id, created_at
            FROM inventory_movements
            WHERE warehouse_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (warehouse_id, limit),
        )
        rows = cursor.fetchall()

    items = []
    for row in rows:
        item = dict(row)
        if item.get("created_at") is not None:
            item["created_at"] = item["created_at"].isoformat()
        items.append(item)

    return {
        "warehouse_id": warehouse_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "type": "MOVEMENTS_EXPORT",
        "items": items,
        "totals": {"movements": len(items)},
    }


def handle(event: dict) -> None:
    payload = event.get("payload") or {}
    job_id = payload.get("job_id")
    report_type = payload.get("report_type", "INVENTORY_SNAPSHOT")
    warehouse_id = payload.get("warehouse_id") or settings.WAREHOUSE_ID

    if not job_id:
        logger.warning("report_event_without_job_id event_id=%s", event.get("event_id"))
        return

    connection = get_connection()
    try:
        with get_cursor(connection) as cursor:
            cursor.execute(
                "SELECT status FROM report_jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning("report_job_not_found job_id=%s", job_id)
                connection.rollback()
                return
            if row["status"] == "COMPLETED":
                logger.info("report_job_already_completed job_id=%s", job_id)
                connection.rollback()
                return

            cursor.execute(
                """
                UPDATE report_jobs
                SET status = 'PROCESSING', started_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
        connection.commit()

        if report_type == "MOVEMENTS_EXPORT":
            result = build_movements_export(connection, warehouse_id)
        else:
            result = build_inventory_snapshot(connection, warehouse_id)

        with get_cursor(connection) as cursor:
            cursor.execute(
                """
                UPDATE report_jobs
                SET status = 'COMPLETED', finished_at = NOW(), result = %s
                WHERE id = %s
                """,
                (Json(result), job_id),
            )
        connection.commit()
        logger.info("report_job_completed job_id=%s type=%s", job_id, report_type)

    except Exception as exc:
        connection.rollback()
        logger.exception("report_job_failed job_id=%s", job_id)
        try:
            with get_cursor(connection) as cursor:
                cursor.execute(
                    """
                    UPDATE report_jobs
                    SET status = 'FAILED', finished_at = NOW(), error = %s
                    WHERE id = %s
                    """,
                    (str(exc), job_id),
                )
            connection.commit()
        except Exception:
            logger.exception("report_job_failed_to_mark job_id=%s", job_id)
    finally:
        connection.close()


if __name__ == "__main__":
    consume(QUEUE, handle)
