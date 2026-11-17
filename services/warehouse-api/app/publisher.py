import json
import logging
import time
from typing import Any

import pika
from warehouse_common.events import build_event, routing_key_for

from app.config import settings

logger = logging.getLogger("warehouse.publisher")


class EventPublisher:
    """Publica eventos en RabbitMQ sin bloquear la operación principal.

    Si RabbitMQ está caído, la API sigue funcionando. Se usa un circuit
    breaker simple: tras un fallo, no se intenta publicar durante unos
    segundos para no castigar cada request con un timeout.
    En Fase 10 se agrega Outbox para que la publicación sea confiable.
    """

    def __init__(
        self,
        enabled: bool,
        url: str,
        exchange: str,
        cooldown_seconds: int = 10,
    ) -> None:
        self.enabled = enabled
        self.url = url
        self.exchange = exchange
        self.cooldown_seconds = cooldown_seconds
        self._disabled_until = 0.0

    def _available(self) -> bool:
        return self.enabled and time.monotonic() >= self._disabled_until

    def _open_channel(self):
        parameters = pika.URLParameters(self.url)
        parameters.connection_attempts = 1
        parameters.retry_delay = 0
        parameters.socket_timeout = 1
        parameters.blocked_connection_timeout = 1
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.exchange_declare(
            exchange=self.exchange,
            exchange_type="topic",
            durable=True,
        )
        return connection, channel

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: str,
    ) -> bool:
        return self.publish_many([(event_type, payload)], correlation_id)

    def publish_many(
        self,
        events: list[tuple[str, dict[str, Any]]],
        correlation_id: str,
    ) -> bool:
        if not events or not self._available():
            return False

        connection = None
        try:
            connection, channel = self._open_channel()
            for event_type, payload in events:
                event = build_event(
                    event_type=event_type,
                    source=settings.WAREHOUSE_ID,
                    payload=payload,
                    correlation_id=correlation_id,
                )
                routing_key = routing_key_for(event_type, settings.WAREHOUSE_ID)
                channel.basic_publish(
                    exchange=self.exchange,
                    routing_key=routing_key,
                    body=json.dumps(event).encode("utf-8"),
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,
                        correlation_id=correlation_id,
                        message_id=event["event_id"],
                    ),
                )
                logger.info(
                    "event_published",
                    extra={
                        "extra_fields": {
                            "event_id": event["event_id"],
                            "event_type": event_type,
                            "routing_key": routing_key,
                            "correlation_id": correlation_id,
                        }
                    },
                )
            self._disabled_until = 0.0
            return True
        except Exception as exc:
            self._disabled_until = time.monotonic() + self.cooldown_seconds
            logger.warning(
                "event_publish_failed error=%s cooldown_seconds=%s",
                exc,
                self.cooldown_seconds,
            )
            return False
        finally:
            if connection is not None and connection.is_open:
                connection.close()


publisher = EventPublisher(
    enabled=settings.RABBITMQ_ENABLED,
    url=settings.RABBITMQ_URL,
    exchange=settings.RABBITMQ_EXCHANGE,
)
