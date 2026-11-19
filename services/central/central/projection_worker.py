"""Projection worker (fase 7): mantiene el read model global_inventory.

Escucha warehouse.*.INVENTORY_UPDATED de todas las bodegas y guarda el ultimo
stock conocido de cada sku en cada bodega.
"""

import json
import logging
import signal
import sys
import time

import pika
from pika.exceptions import AMQPError

from central.config import PROJECTION_QUEUE, PROJECTION_ROUTING_KEY, settings
from central.database import SessionLocal, init_db
from central.projection import parse_inventory_event
from central.read_model import rebuild, upsert

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("central.projection")


def handle(body: bytes) -> None:
    event = json.loads(body)
    row = parse_inventory_event(event)
    if not row:
        return
    with SessionLocal() as db:
        applied = upsert(db, row)
    logger.info(
        "projection %s event_id=%s warehouse=%s sku=%s quantity=%s",
        "applied" if applied else "skipped_old_or_duplicate",
        event.get("event_id"),
        row["warehouse_id"],
        row["sku"],
        row["quantity"],
    )


def stop(*_args):
    logger.info("projection_worker_stopping")
    sys.exit(0)


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    init_db()
    with SessionLocal() as db:
        logger.info("rebuild_on_start result=%s", rebuild(db))

    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
            channel = connection.channel()
            channel.exchange_declare(
                exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True
            )
            channel.queue_declare(queue=PROJECTION_QUEUE, durable=True)
            channel.queue_bind(
                exchange=settings.RABBITMQ_EXCHANGE,
                queue=PROJECTION_QUEUE,
                routing_key=PROJECTION_ROUTING_KEY,
            )
            channel.basic_qos(prefetch_count=50)

            def callback(ch, method, _props, body):
                try:
                    handle(body)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception:
                    # ej: central-db caida. Se devuelve a la cola para no perder el evento
                    logger.exception("projection_failed")
                    time.sleep(1)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            channel.basic_consume(queue=PROJECTION_QUEUE, on_message_callback=callback)
            logger.info("projection_worker_started queue=%s", PROJECTION_QUEUE)
            channel.start_consuming()
        except AMQPError as exc:
            logger.warning("rabbitmq_error error=%s, reconectando", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
