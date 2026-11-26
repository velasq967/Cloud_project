"""Projection worker (fase 7): mantiene el read model global_inventory.

Escucha warehouse.*.INVENTORY_UPDATED de todas las bodegas y guarda el ultimo
stock conocido de cada sku en cada bodega.

Fase 10: un mensaje nunca vuelve a la cola en un bucle infinito.
- JSON roto o evento mal formado -> DLQ directo (reintentar no lo arregla).
- central-db caida u otro error temporal -> se reintenta con espera creciente
  (cola .retry con TTL) hasta PROJECTION_MAX_ATTEMPTS, luego DLQ.
  Lo que quede en la DLQ se puede corregir con POST /global/rebuild.
"""

import json
import logging
import signal
import sys
import time

import pika
from pika.exceptions import AMQPError
from sqlalchemy.exc import DataError, IntegrityError

from central.config import (
    PROJECTION_DLQ,
    PROJECTION_MAX_ATTEMPTS,
    PROJECTION_QUEUE,
    PROJECTION_RETRY_QUEUE,
    PROJECTION_ROUTING_KEY,
    settings,
)
from central.database import SessionLocal, init_db
from central.projection import parse_inventory_event
from central.read_model import rebuild, upsert

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("central.projection")

BASE_BACKOFF_MS = 1000


class InvalidEvent(Exception):
    """El evento no se puede aplicar nunca: va directo a la DLQ."""


def decode(body: bytes) -> dict | None:
    """Devuelve la fila a aplicar, None si el evento no aplica, o lanza InvalidEvent."""
    try:
        event = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidEvent(f"invalid_json: {exc}") from exc
    if not isinstance(event, dict):
        raise InvalidEvent("el mensaje no es un objeto JSON")

    row = parse_inventory_event(event)
    if row is None:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("event_type") == "INVENTORY_UPDATED" and payload.get("sku"):
            # trae sku pero cantidades o fecha invalidas: es un evento roto
            raise InvalidEvent("INVENTORY_UPDATED con campos invalidos")
        # otro tipo de evento o evento viejo sin sku: se ignora a proposito
        return None
    row["_event_id"] = event.get("event_id")
    return row


def is_retryable(exc: Exception) -> bool:
    # evento roto o dato que la base rechaza: reintentar no sirve
    if isinstance(exc, (InvalidEvent, DataError, IntegrityError)):
        return False
    # central-db caida (OperationalError), timeouts, etc: puede ser temporal
    return True


def decide(attempt: int, exc: Exception) -> str:
    if not is_retryable(exc):
        return "dlq"
    return "retry" if attempt < PROJECTION_MAX_ATTEMPTS else "dlq"


def backoff_ms(attempt: int) -> int:
    return BASE_BACKOFF_MS * (2 ** (attempt - 1))  # 1s, 2s, 4s, 8s


def apply(row: dict) -> bool:
    event_id = row.pop("_event_id", None)
    with SessionLocal() as db:
        applied = upsert(db, row)
    logger.info(
        "projection %s event_id=%s warehouse=%s sku=%s quantity=%s",
        "applied" if applied else "skipped_old_or_duplicate",
        event_id,
        row["warehouse_id"],
        row["sku"],
        row["quantity"],
    )
    return applied


def _props(properties, headers, expiration=None):
    return pika.BasicProperties(
        content_type="application/json",
        delivery_mode=2,
        correlation_id=getattr(properties, "correlation_id", None),
        message_id=getattr(properties, "message_id", None),
        headers=headers,
        expiration=expiration,
    )


def handle_delivery(ch, method, properties, body, apply_fn=apply) -> str:
    """Procesa un mensaje y devuelve applied/ignored/retry/dlq. Siempre hace ack."""
    headers = dict(getattr(properties, "headers", None) or {})
    attempt = int(headers.get("x-retry-count", 0)) + 1
    try:
        row = decode(body)
        if row is None:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return "ignored"
        apply_fn(row)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return "applied"
    except Exception as exc:
        reason = f"{exc.__class__.__name__}: {exc}"
        if decide(attempt, exc) == "retry":
            delay = backoff_ms(attempt)
            headers["x-retry-count"] = attempt
            ch.basic_publish(
                exchange="",
                routing_key=PROJECTION_RETRY_QUEUE,
                body=body,
                properties=_props(properties, headers, expiration=str(delay)),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.warning(
                "projection_retry_scheduled attempt=%s/%s delay_ms=%s error=%s",
                attempt,
                PROJECTION_MAX_ATTEMPTS,
                delay,
                reason,
            )
            return "retry"

        headers.update({"x-attempts": attempt, "x-error-reason": reason[:200]})
        ch.basic_publish(
            exchange="",
            routing_key=PROJECTION_DLQ,
            body=body,
            properties=_props(properties, headers),
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.error("projection_sent_to_dlq attempts=%s reason=%s", attempt, reason)
        return "dlq"


def declare(channel) -> None:
    channel.exchange_declare(
        exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True
    )
    channel.queue_declare(queue=PROJECTION_QUEUE, durable=True)
    channel.queue_bind(
        exchange=settings.RABBITMQ_EXCHANGE,
        queue=PROJECTION_QUEUE,
        routing_key=PROJECTION_ROUTING_KEY,
    )
    # cola de espera: al vencer el TTL del mensaje vuelve a la cola principal
    channel.queue_declare(
        queue=PROJECTION_RETRY_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": PROJECTION_QUEUE,
        },
    )
    channel.queue_declare(queue=PROJECTION_DLQ, durable=True)


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
            declare(channel)
            channel.basic_qos(prefetch_count=50)

            def callback(ch, method, properties, body):
                handle_delivery(ch, method, properties, body)

            channel.basic_consume(queue=PROJECTION_QUEUE, on_message_callback=callback)
            logger.info(
                "projection_worker_started queue=%s retry=%s dlq=%s",
                PROJECTION_QUEUE,
                PROJECTION_RETRY_QUEUE,
                PROJECTION_DLQ,
            )
            channel.start_consuming()
        except AMQPError as exc:
            logger.warning("rabbitmq_error error=%s, reconectando", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
