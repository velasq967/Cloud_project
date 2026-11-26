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

    def publish_now(self, event_ids: list[int]) -> int:
        """Publica solo los eventos indicados (los de la operación actual).

        Se llama justo después del commit. Usa una sola conexión a RabbitMQ y
        no toca el resto de pendientes: de esos se encarga el outbox worker,
        así un atraso acumulado no hace más lento cada request.
        """
        if not event_ids:
            return 0
        query = (
            self.db.query(OutboxEventEntity)
            .filter(OutboxEventEntity.id.in_(event_ids))
            .filter(OutboxEventEntity.published_at.is_(None))
            .order_by(OutboxEventEntity.id)
        )
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        rows = query.all()
        if not rows:
            self.db.commit()
            return 0

        published = publisher.publish_batch([(row.payload, row.routing_key) for row in rows])
        now = datetime.now(timezone.utc)
        for index, row in enumerate(rows):
            row.attempts += 1
            if index < published:
                row.published_at = now
                row.last_error = None
            else:
                row.last_error = "publish_failed"
        if published < len(rows):
            logger.warning(
                "outbox_inline_publish_incomplete published=%s pending=%s",
                published,
                len(rows) - published,
            )
        self.db.commit()
        return published

    def publish_pending(self, limit: int = 50) -> int:
        """Publica cualquier pendiente. Ya no se usa en el request (ver publish_now);
        queda para tareas manuales y tests. El outbox worker hace lo mismo en segundo plano."""
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
