import json
import logging
import time
from collections.abc import Callable
from typing import Any

import pika

from shared.config import settings
from shared.idempotency import already_processed, mark_processed
from shared.metrics import (
    DLQ_MESSAGES,
    MESSAGE_DURATION,
    MESSAGES_PROCESSED,
    RETRIES,
    start_metrics_server,
)

logger = logging.getLogger("worker.rabbit")

EXCHANGE = settings.RABBITMQ_EXCHANGE
DLX_EXCHANGE = f"{EXCHANGE}.dlx"
WAREHOUSE_ID = settings.WAREHOUSE_ID
MAX_RETRIES = 3


def queue_name(base: str, warehouse_id: str = WAREHOUSE_ID) -> str:
    # cada bodega tiene sus colas, ej: cache.inventory.WH-001.q
    return f"{base}.{warehouse_id}.q"


def dlq_name(queue: str) -> str:
    # ej: audit.events.WH-001.q -> audit.events.WH-001.dlq
    return queue[:-2] + ".dlq" if queue.endswith(".q") else f"{queue}.dlq"


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
            logger.warning("rabbitmq_not_ready attempt=%s error=%s", attempt, exc)
            time.sleep(delay)
    raise RuntimeError(f"RabbitMQ no respondió: {last_error}")


def declare_topology(channel) -> None:
    channel.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="topic",
        durable=True,
    )
    channel.exchange_declare(
        exchange=DLX_EXCHANGE,
        exchange_type="direct",
        durable=True,
    )
    for queue, routing_keys in QUEUES.items():
        # Cola principal (durable para sobrevivir reinicios)
        channel.queue_declare(queue=queue, durable=True)
        for routing_key in routing_keys:
            channel.queue_bind(
                exchange=EXCHANGE,
                queue=queue,
                routing_key=routing_key,
            )

        # Cola DLQ asociada (Fase 10)
        dead_queue = dlq_name(queue)
        channel.queue_declare(queue=dead_queue, durable=True)
        channel.queue_bind(
            exchange=DLX_EXCHANGE,
            queue=dead_queue,
            routing_key=dead_queue,
        )


def publish_event(event: dict[str, Any], routing_key: str) -> None:
    """Publica un evento ya construido. Usado por el outbox worker."""
    parameters = pika.URLParameters(settings.RABBITMQ_URL)
    parameters.connection_attempts = 1
    parameters.retry_delay = 0
    parameters.socket_timeout = 2
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        channel.exchange_declare(
            exchange=EXCHANGE,
            exchange_type="topic",
            durable=True,
        )
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(event).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                correlation_id=event.get("correlation_id"),
                message_id=event.get("event_id"),
            ),
        )
    finally:
        if connection.is_open:
            connection.close()


def _send_to_dlq(channel, queue: str, body: bytes, reason: str, retry_count: int) -> None:
    dead_queue = dlq_name(queue)
    channel.basic_publish(
        exchange=DLX_EXCHANGE,
        routing_key=dead_queue,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2,  # mensaje persistente en disco
            headers={
                "x-original-queue": queue,
                "x-retry-count": retry_count,
                "x-error-reason": reason[:200],
            },
        ),
    )
    logger.error(
        "message_sent_to_dlq queue=%s dlq=%s retries=%s reason=%s",
        queue,
        dead_queue,
        retry_count,
        reason,
    )


def consume(
    queue: str,
    handler: Callable[[dict[str, Any]], None],
    consumer: str | None = None,
) -> None:
    start_metrics_server()
    connection = connect_with_retry()
    channel = connection.channel()
    channel.basic_qos(prefetch_count=10)
    declare_topology(channel)

    consumer_name = consumer or queue

    def callback(ch, method, properties, body):
        started = time.perf_counter()
        headers = dict((properties.headers or {}))
        retry_count = int(headers.get("x-retry-count", 0))

        # 1. Validar JSON: si está roto, NO se reintenta -> directo a DLQ
        try:
            event = json.loads(body)
        except json.JSONDecodeError as exc:
            MESSAGES_PROCESSED.labels(queue=queue, status="invalid").inc()
            DLQ_MESSAGES.labels(queue=queue).inc()
            _send_to_dlq(ch, queue, body, f"invalid_json: {exc}", retry_count)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2. Idempotencia persistente: si el consumidor ya procesó el evento,
        #    se ignora aunque el worker se haya reiniciado.
        event_id = event.get("event_id")
        try:
            if event_id and already_processed(event_id, consumer_name):
                MESSAGES_PROCESSED.labels(queue=queue, status="duplicate").inc()
                logger.info(
                    "duplicate_event_ignored queue=%s consumer=%s event_id=%s",
                    queue,
                    consumer_name,
                    event_id,
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            handler(event)
            if event_id:
                mark_processed(event_id, consumer_name)
            MESSAGE_DURATION.labels(queue=queue).observe(
                time.perf_counter() - started
            )
            MESSAGES_PROCESSED.labels(queue=queue, status="success").inc()
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            next_retry = retry_count + 1
            if next_retry <= MAX_RETRIES:
                RETRIES.labels(queue=queue).inc()
                MESSAGES_PROCESSED.labels(queue=queue, status="retry").inc()
                backoff_seconds = 2 ** retry_count  # 1s, 2s, 4s
                logger.warning(
                    "message_retry queue=%s attempt=%s/%s backoff=%ss error=%s",
                    queue,
                    next_retry,
                    MAX_RETRIES,
                    backoff_seconds,
                    exc,
                )
                time.sleep(backoff_seconds)
                headers["x-retry-count"] = next_retry
                ch.basic_publish(
                    exchange="",
                    routing_key=queue,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        headers=headers,
                    ),
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                MESSAGES_PROCESSED.labels(queue=queue, status="dlq").inc()
                DLQ_MESSAGES.labels(queue=queue).inc()
                _send_to_dlq(ch, queue, body, str(exc), retry_count)
                ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue, on_message_callback=callback)
    logger.info("worker_started queue=%s dlq=%s", queue, dlq_name(queue))
    channel.start_consuming()