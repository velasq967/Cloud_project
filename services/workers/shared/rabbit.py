import json
import logging
import time
from collections.abc import Callable
from typing import Any

import pika
from pika.exceptions import AMQPError

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

# Attempt 1 -> Attempt 2 -> Attempt 3 -> DLQ (como el diagrama de la fase 10)
MAX_ATTEMPTS = 3
BASE_BACKOFF_MS = 1000  # espera antes del intento 2: 1s, antes del 3: 2s


class NonRetryableError(Exception):
    """Error que no se arregla reintentando (dato inválido, recurso que no existe).

    El mensaje va directo a la DLQ, sin reintentos.
    """


def is_retryable(exc: Exception) -> bool:
    """Decide si vale la pena reintentar.

    - NonRetryableError: no (error de negocio, ej. el job o producto no existe).
    - KeyError / TypeError / ValueError: no, el evento viene mal formado.
    - Errores de datos de PostgreSQL (constraint, tipo inválido): no.
    - Todo lo demás (DB caída, Redis caído, timeout): sí, puede ser temporal.
    """
    if isinstance(exc, (NonRetryableError, KeyError, TypeError, ValueError)):
        return False
    try:
        import psycopg2

        if isinstance(exc, (psycopg2.DataError, psycopg2.IntegrityError, psycopg2.ProgrammingError)):
            return False
    except ImportError:  # pragma: no cover
        pass
    return True


def backoff_ms(attempt: int) -> int:
    """Espera antes del siguiente intento. attempt es el intento que acaba de fallar (1, 2...)."""
    return BASE_BACKOFF_MS * (2 ** (attempt - 1))


def decide(attempt: int, exc: Exception) -> str:
    """'retry' o 'dlq' según el tipo de error y el número de intento que falló."""
    if not is_retryable(exc):
        return "dlq"
    return "retry" if attempt < MAX_ATTEMPTS else "dlq"


def queue_name(base: str, warehouse_id: str = WAREHOUSE_ID) -> str:
    # cada bodega tiene sus colas, ej: cache.inventory.WH-001.q
    return f"{base}.{warehouse_id}.q"


def dlq_name(queue: str) -> str:
    # ej: audit.events.WH-001.q -> audit.events.WH-001.dlq
    return queue[:-2] + ".dlq" if queue.endswith(".q") else f"{queue}.dlq"


def retry_queue_name(queue: str) -> str:
    # ej: audit.events.WH-001.q -> audit.events.WH-001.retry
    return queue[:-2] + ".retry" if queue.endswith(".q") else f"{queue}.retry"


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

        # Cola de espera para reintentos: nadie la consume. Cada mensaje lleva
        # su propio TTL (expiration); al vencer, RabbitMQ lo devuelve a la cola
        # principal. Así el worker no se queda dormido esperando el backoff.
        channel.queue_declare(
            queue=retry_queue_name(queue),
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": queue,
            },
        )

        # Cola DLQ asociada (Fase 10)
        dead_queue = dlq_name(queue)
        channel.queue_declare(queue=dead_queue, durable=True)
        channel.queue_bind(
            exchange=DLX_EXCHANGE,
            queue=dead_queue,
            routing_key=dead_queue,
        )


def open_publisher_channel():
    """Abre una conexión corta para publicar. Devuelve (connection, channel)."""
    parameters = pika.URLParameters(settings.RABBITMQ_URL)
    parameters.connection_attempts = 1
    parameters.retry_delay = 0
    parameters.socket_timeout = 2
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    return connection, channel


def publish_event(event: dict[str, Any], routing_key: str, channel=None) -> None:
    """Publica un evento ya construido. Usado por el outbox worker.

    Si se pasa un canal abierto se reutiliza; si no, se abre una conexión propia.
    """
    if channel is not None:
        _basic_publish(channel, event, routing_key)
        return

    connection, channel = open_publisher_channel()
    try:
        _basic_publish(channel, event, routing_key)
    finally:
        if connection.is_open:
            connection.close()


def _basic_publish(channel, event: dict[str, Any], routing_key: str) -> None:
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


def _copy_properties(properties, headers: dict, expiration: str | None = None):
    """Conserva correlation_id, message_id y content_type al republicar."""
    return pika.BasicProperties(
        content_type=getattr(properties, "content_type", None) or "application/json",
        delivery_mode=2,  # mensaje persistente en disco
        correlation_id=getattr(properties, "correlation_id", None),
        message_id=getattr(properties, "message_id", None),
        headers=headers,
        expiration=expiration,
    )


def _send_to_dlq(channel, queue: str, body: bytes, properties, reason: str, attempts: int) -> None:
    dead_queue = dlq_name(queue)
    headers = dict(getattr(properties, "headers", None) or {})
    headers.update(
        {
            "x-original-queue": queue,
            "x-attempts": attempts,
            "x-error-reason": reason[:200],
        }
    )
    channel.basic_publish(
        exchange=DLX_EXCHANGE,
        routing_key=dead_queue,
        body=body,
        properties=_copy_properties(properties, headers),
    )
    logger.error(
        "message_sent_to_dlq queue=%s dlq=%s attempts=%s reason=%s correlation_id=%s",
        queue,
        dead_queue,
        attempts,
        reason,
        getattr(properties, "correlation_id", None),
    )


def _schedule_retry(channel, queue: str, body: bytes, properties, attempt: int, delay_ms: int) -> None:
    headers = dict(getattr(properties, "headers", None) or {})
    headers["x-retry-count"] = attempt  # intentos fallidos hasta ahora
    channel.basic_publish(
        exchange="",
        routing_key=retry_queue_name(queue),
        body=body,
        properties=_copy_properties(properties, headers, expiration=str(delay_ms)),
    )


def handle_delivery(
    ch,
    method,
    properties,
    body: bytes,
    *,
    queue: str,
    handler: Callable[[dict[str, Any]], None],
    consumer_name: str,
    on_dead_letter: Callable[[dict[str, Any], str], None] | None = None,
) -> str:
    """Procesa un mensaje y devuelve el resultado: success, duplicate, retry o dlq.

    Siempre hace ack: el mensaje termina procesado, programado para reintento
    (en la cola .retry) o en la DLQ. Nunca queda en un bucle infinito.
    """
    started = time.perf_counter()
    headers = dict(getattr(properties, "headers", None) or {})
    attempt = int(headers.get("x-retry-count", 0)) + 1  # intento actual

    # 1. JSON roto: reintentar no lo arregla -> directo a DLQ
    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("el mensaje no es un objeto JSON")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        MESSAGES_PROCESSED.labels(queue=queue, status="invalid").inc()
        DLQ_MESSAGES.labels(queue=queue).inc()
        _send_to_dlq(ch, queue, body, properties, f"invalid_json: {exc}", attempt)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return "dlq"

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
            return "duplicate"

        handler(event)
        if event_id:
            mark_processed(event_id, consumer_name)
        MESSAGE_DURATION.labels(queue=queue).observe(time.perf_counter() - started)
        MESSAGES_PROCESSED.labels(queue=queue, status="success").inc()
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return "success"

    except Exception as exc:
        reason = f"{exc.__class__.__name__}: {exc}"
        if decide(attempt, exc) == "retry":
            delay = backoff_ms(attempt)
            RETRIES.labels(queue=queue).inc()
            MESSAGES_PROCESSED.labels(queue=queue, status="retry").inc()
            logger.warning(
                "message_retry_scheduled queue=%s attempt=%s/%s delay_ms=%s event_id=%s "
                "correlation_id=%s error=%s",
                queue,
                attempt,
                MAX_ATTEMPTS,
                delay,
                event_id,
                event.get("correlation_id"),
                reason,
            )
            _schedule_retry(ch, queue, body, properties, attempt, delay)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return "retry"

        MESSAGES_PROCESSED.labels(queue=queue, status="dlq").inc()
        DLQ_MESSAGES.labels(queue=queue).inc()
        _send_to_dlq(ch, queue, body, properties, reason, attempt)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        if on_dead_letter is not None:
            try:
                on_dead_letter(event, reason)
            except Exception:
                logger.exception("on_dead_letter_failed queue=%s event_id=%s", queue, event_id)
        return "dlq"


def consume(
    queue: str,
    handler: Callable[[dict[str, Any]], None],
    consumer: str | None = None,
    on_dead_letter: Callable[[dict[str, Any], str], None] | None = None,
) -> None:
    start_metrics_server()
    consumer_name = consumer or queue

    def callback(ch, method, properties, body):
        handle_delivery(
            ch,
            method,
            properties,
            body,
            queue=queue,
            handler=handler,
            consumer_name=consumer_name,
            on_dead_letter=on_dead_letter,
        )

    # Si RabbitMQ se reinicia, el worker se reconecta en vez de morir.
    while True:
        try:
            connection = connect_with_retry()
            channel = connection.channel()
            channel.basic_qos(prefetch_count=10)
            declare_topology(channel)
            channel.basic_consume(queue=queue, on_message_callback=callback)
            logger.info(
                "worker_started queue=%s retry=%s dlq=%s",
                queue,
                retry_queue_name(queue),
                dlq_name(queue),
            )
            channel.start_consuming()
        except AMQPError as exc:
            logger.warning("rabbitmq_connection_lost queue=%s error=%s, reconectando", queue, exc)
            time.sleep(3)
