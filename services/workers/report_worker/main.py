import logging
from datetime import datetime, timezone

from psycopg2.extras import Json
from shared.config import settings
from shared.db import get_connection, get_cursor
from shared.logging import configure_worker_logging
from shared.rabbit import NonRetryableError, consume, queue_name

configure_worker_logging("report-worker")
logger = logging.getLogger("worker.report")

QUEUE = queue_name("report.jobs")
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

    # Errores de datos: reintentar no los arregla -> DLQ directo.
    if not job_id:
        raise NonRetryableError("evento REPORT_REQUESTED sin job_id")
    if report_type not in ("INVENTORY_SNAPSHOT", "MOVEMENTS_EXPORT"):
        raise NonRetryableError(f"tipo de reporte desconocido: {report_type}")

    connection = get_connection()
    try:
        with get_cursor(connection) as cursor:
            cursor.execute(
                "SELECT status FROM report_jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                connection.rollback()
                raise NonRetryableError(f"report job {job_id} no existe")
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
                SET status = 'COMPLETED', finished_at = NOW(), result = %s, error = NULL
                WHERE id = %s
                """,
                (Json(result), job_id),
            )
        connection.commit()
        logger.info("report_job_completed job_id=%s type=%s", job_id, report_type)

    except NonRetryableError:
        raise
    except Exception as exc:
        # Antes el error se marcaba FAILED y se tragaba, así que el reintento
        # y la DLQ nunca se activaban. Ahora se deja el job en RETRYING y se
        # relanza: la capa de RabbitMQ decide si reintenta o lo manda a la DLQ.
        connection.rollback()
        logger.warning("report_job_attempt_failed job_id=%s error=%s", job_id, exc)
        _mark(job_id, "RETRYING", str(exc), connection)
        raise
    finally:
        connection.close()


def _mark(job_id: str, status: str, error: str, connection=None) -> None:
    """Marca el estado del job sin ocultar el error original si la DB tampoco responde."""
    own = connection is None
    try:
        connection = connection or get_connection()
        with get_cursor(connection) as cursor:
            cursor.execute(
                """
                UPDATE report_jobs
                SET status = %s, error = %s,
                    finished_at = CASE WHEN %s = 'FAILED' THEN NOW() ELSE finished_at END
                WHERE id = %s AND status <> 'COMPLETED'
                """,
                (status, error[:1000], status, job_id),
            )
        connection.commit()
    except Exception:
        logger.exception("report_job_mark_failed job_id=%s status=%s", job_id, status)
    finally:
        if own and connection is not None:
            connection.close()


def on_dead_letter(event: dict, reason: str) -> None:
    """Se llama cuando el mensaje termina en la DLQ: el job queda FAILED."""
    job_id = (event.get("payload") or {}).get("job_id")
    if job_id:
        _mark(job_id, "FAILED", f"enviado a DLQ: {reason}")


if __name__ == "__main__":
    consume(QUEUE, handle, on_dead_letter=on_dead_letter)
