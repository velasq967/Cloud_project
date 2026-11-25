import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from warehouse_common.events import build_event, routing_key_for

from app.config import settings
from app.modules.outbox.models import OutboxEventEntity
from app.publisher import publisher

logger = logging.getLogger("warehouse.outbox")


class OutboxService:
    """Outbox transaccional.

    El evento se guarda en la misma transacción que el movimiento de
    inventario. Después del commit se intenta publicar; si RabbitMQ está
    caído, el outbox worker lo reintenta sin perder el evento.
    """

    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        events: list[tuple[str, dict]],
        correlation_id: str,
    ) -> list[OutboxEventEntity]:
        rows = []
        for event_type, payload in events:
            event = build_event(
                event_type=event_type,
                source=settings.WAREHOUSE_ID,
                payload=payload,
                correlation_id=correlation_id,
            )
            row = OutboxEventEntity(
                event_id=event["event_id"],
                event_type=event_type,
                routing_key=routing_key_for(event_type, settings.WAREHOUSE_ID),
                correlation_id=correlation_id,
                payload=event,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def publish_pending(self, limit: int = 50) -> int:
        query = (
            self.db.query(OutboxEventEntity)
            .filter(OutboxEventEntity.published_at.is_(None))
            .order_by(OutboxEventEntity.id)
            .limit(limit)
        )
        # SKIP LOCKED evita que dos réplicas de la API publiquen lo mismo.
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        rows = query.all()
        published = 0
        for row in rows:
            ok = publisher.publish_event(row.payload, row.routing_key)
            row.attempts += 1
            if ok:
                row.published_at = datetime.now(timezone.utc)
                row.last_error = None
                published += 1
            else:
                row.last_error = "publish_failed"
                logger.warning(
                    "outbox_publish_failed event_id=%s event_type=%s",
                    row.event_id,
                    row.event_type,
                )
        self.db.commit()
        return published
