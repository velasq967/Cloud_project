"""Contrato de eventos de la plataforma.

El sobre (envelope) es común a todos los eventos para permitir versionado,
trazabilidad e idempotencia. El payload cambia según event_type.
"""

import uuid
from datetime import datetime, timezone
from typing import Any


class EventTypes:
    INVENTORY_UPDATED = "INVENTORY_UPDATED"
    INVENTORY_MOVEMENT_REGISTERED = "INVENTORY_MOVEMENT_REGISTERED"
    TRANSFER_REQUESTED = "TRANSFER_REQUESTED"
    TRANSFER_STEP_COMPLETED = "TRANSFER_STEP_COMPLETED"
    TRANSFER_COMPLETED = "TRANSFER_COMPLETED"
    TRANSFER_FAILED = "TRANSFER_FAILED"
    REPORT_REQUESTED = "REPORT_REQUESTED"
    REPORT_COMPLETED = "REPORT_COMPLETED"
    REPORT_FAILED = "REPORT_FAILED"
    IOT_READING_RECEIVED = "IOT_READING_RECEIVED"
    IOT_ALERT_RAISED = "IOT_ALERT_RAISED"


def build_event(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    correlation_id: str,
    event_version: int = 1,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or f"EVT-{uuid.uuid4()}",
        "event_type": event_type,
        "event_version": event_version,
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
        "correlation_id": correlation_id,
        "source": source,
        "payload": payload,
    }


def routing_key_for(event_type: str, warehouse_id: str) -> str:
    """Routing key usada en RabbitMQ.

    Ejemplo: warehouse.WH-001.INVENTORY_UPDATED
    """
    return f"warehouse.{warehouse_id}.{event_type}"
