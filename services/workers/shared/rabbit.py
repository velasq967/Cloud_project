import json
import logging
import time
from collections.abc import Callable
from typing import Any

import pika

from shared.config import settings

logger = logging.getLogger("worker.rabbit")

EXCHANGE = settings.RABBITMQ_EXCHANGE
WAREHOUSE_ID = settings.WAREHOUSE_ID


def queue_name(base: str, warehouse_id: str = WAREHOUSE_ID) -> str:
    # cada bodega tiene sus colas, ej: cache.inventory.WH-001.q
    return f"{base}.{warehouse_id}.q"


def build_queues(warehouse_id: str = WAREHOUSE_ID) -> dict[str, list[str]]:
    prefix = f"warehouse.{warehouse_id}"
    return {
        queue_name("cache.inventory", warehouse_id): [
            f"{prefix}.INVENTORY_UPDATED",
        ],
        queue_name("audit.events", warehouse_id): [
            f"{prefix}.INVENTORY_UPDATED",
            f"{prefix}.INVENTORY_MOVEMENT_REGISTERED",
        ],
        queue_name("report.jobs", warehouse_id): [
            f"{prefix}.REPORT_REQUESTED",
        ],
    }


QUEUES = build_queues()


def connect_with_retry(attempts: int = 60, delay: int = 2) -> pika.BlockingConnection:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            parameters = pika.URLParameters(settings.RABBITMQ_URL)
            return pika.BlockingConnection(parameters)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "rabbitmq_not_ready attempt=%s error=%s", attempt, exc
            )
            time.sleep(delay)
    raise RuntimeError(f"RabbitMQ no respondió: {last_error}")


def declare_topology(channel) -> None:
    channel.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="topic",
        durable=True,
    )
    for queue, routing_keys in QUEUES.items():
        channel.queue_declare(queue=queue, durable=True)
        for routing_key in routing_keys:
            channel.queue_bind(
                exchange=EXCHANGE,
                queue=queue,
                routing_key=routing_key,
            )


def consume(queue: str, handler: Callable[[dict[str, Any]], None]) -> None:
    connection = connect_with_retry()
    channel = connection.channel()
    channel.basic_qos(prefetch_count=10)
    declare_topology(channel)

    def callback(ch, method, properties, body):
        try:
            event = json.loads(body)
            handler(event)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception(
                "message_processing_failed queue=%s delivery_tag=%s",
                queue,
                method.delivery_tag,
            )
            # Fase 10 reemplaza esto por reintentos con backoff y DLQ.
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=queue, on_message_callback=callback)
    logger.info("worker_started queue=%s", queue)
    channel.start_consuming()
