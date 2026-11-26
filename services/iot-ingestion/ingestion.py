"""Validación y transformación MQTT -> evento de dominio."""

import uuid
from datetime import datetime, timezone

from warehouse_common.events import EventTypes, build_event, routing_key_for


def parse_topic(topic: str) -> tuple[str, str]:
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "warehouses" or parts[2] != "sensors":
        raise ValueError(f"Topic inválido: {topic}")
    return parts[1], parts[3]


def validate_reading(payload: dict, warehouse_id: str, sensor_id: str) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("El payload no es un objeto JSON")

    declared_warehouse = payload.get("warehouse_id")
    if declared_warehouse and declared_warehouse != warehouse_id:
        raise ValueError(
            f"warehouse_id del payload ({declared_warehouse}) no coincide con el topic ({warehouse_id})"
        )

    declared_sensor = payload.get("sensor_id")
    if declared_sensor and declared_sensor != sensor_id:
        raise ValueError(
            f"sensor_id del payload ({declared_sensor}) no coincide con el topic ({sensor_id})"
        )

    sensor_type = payload.get("sensor_type")
    if not sensor_type:
        raise ValueError("Falta sensor_type")
    try:
        value = float(payload["value"])
        sequence_number = int(payload["sequence_number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"value/sequence_number inválidos: {exc}") from exc

    occurred_at = payload.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    return {
        "event_id": payload.get("event_id") or f"IOT-{uuid.uuid4()}",
        "warehouse_id": warehouse_id,
        "sensor_id": sensor_id,
        "sensor_type": str(sensor_type),
        "value": value,
        "unit": str(payload.get("unit", "")),
        "sequence_number": sequence_number,
        "occurred_at": occurred_at,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def build_iot_event(reading: dict) -> tuple[dict, str]:
    occurred_at = None
    try:
        occurred_at = datetime.fromisoformat(
            str(reading["occurred_at"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        occurred_at = datetime.now(timezone.utc)

    event = build_event(
        event_type=EventTypes.IOT_READING_RECEIVED,
        source=reading["warehouse_id"],
        payload=reading,
        # El event_id del sensor es la llave de idempotencia de todo el flujo.
        # Si se genera uno nuevo aquí, un reenvío del sensor se procesa dos veces.
        event_id=reading["event_id"],
        correlation_id=reading["event_id"],
        occurred_at=occurred_at,
    )
    routing_key = routing_key_for(
        EventTypes.IOT_READING_RECEIVED, reading["warehouse_id"]
    )
    return event, routing_key
