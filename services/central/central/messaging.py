import json
import logging

import pika

from central.config import TRANSFER_QUEUE, TRANSFER_ROUTING_KEY, settings

logger = logging.getLogger("central.messaging")


def declare(channel) -> None:
    channel.exchange_declare(exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue=TRANSFER_QUEUE, durable=True)
    channel.queue_bind(
        exchange=settings.RABBITMQ_EXCHANGE, queue=TRANSFER_QUEUE, routing_key=TRANSFER_ROUTING_KEY
    )


def publish_transfer(transfer_id: str) -> bool:
    """Publica TRANSFER_REQUESTED. Si falla no pasa nada grave:
    el worker revisa la tabla cada pocos segundos y la recoge igual."""
    connection = None
    try:
        params = pika.URLParameters(settings.RABBITMQ_URL)
        params.connection_attempts = 1
        params.socket_timeout = 2
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        declare(channel)
        body = {"event_type": "TRANSFER_REQUESTED", "transfer_id": transfer_id}
        channel.basic_publish(
            exchange=settings.RABBITMQ_EXCHANGE,
            routing_key=TRANSFER_ROUTING_KEY,
            body=json.dumps(body).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                correlation_id=transfer_id,
            ),
        )
        logger.info("transfer_published transfer_id=%s", transfer_id)
        return True
    except Exception as exc:
        logger.warning("transfer_publish_failed transfer_id=%s error=%s", transfer_id, exc)
        return False
    finally:
        if connection is not None and connection.is_open:
            connection.close()
