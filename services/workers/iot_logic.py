"""Reglas puras de IoT, sin base de datos ni MQTT (fáciles de testear)."""

from datetime import datetime


def parse_reading(event: dict) -> dict:
    payload = event.get("payload") or {}
    warehouse_id = payload.get("warehouse_id") or event.get("source")
    sensor_id = payload.get("sensor_id")
    sensor_type = payload.get("sensor_type")
    if not warehouse_id or not sensor_id or not sensor_type:
        raise ValueError("Lectura sin warehouse_id, sensor_id o sensor_type")

    try:
        value = float(payload["value"])
        sequence_number = int(payload["sequence_number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Lectura inválida: {exc}") from exc

    occurred_at = payload.get("occurred_at") or event.get("occurred_at")
    if occurred_at:
        occurred_at = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))

    return {
        "event_id": event.get("event_id"),
        "warehouse_id": warehouse_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": value,
        "unit": payload.get("unit", ""),
        "sequence_number": sequence_number,
        "occurred_at": occurred_at,
    }


def should_update_state(last_sequence: int | None, incoming_sequence: int) -> bool:
    """Solo un evento más nuevo reemplaza el estado; duplicados/viejos no."""
    return last_sequence is None or incoming_sequence > last_sequence


def evaluate_alerts(reading: dict) -> list[dict]:
    sensor_type = reading["sensor_type"]
    value = reading["value"]
    alerts = []

    def add(rule: str, severity: str, message: str):
        alerts.append({"rule": rule, "severity": severity, "message": message})

    if sensor_type == "temperature":
        if value > 8:
            add("TEMP_HIGH", "HIGH", f"Temperatura alta: {value:.1f} °C")
        elif value < 2:
            add("TEMP_LOW", "HIGH", f"Temperatura baja: {value:.1f} °C")
    elif sensor_type == "humidity":
        if value > 70:
            add("HUMIDITY_HIGH", "MEDIUM", f"Humedad alta: {value:.1f} %")
        elif value < 30:
            add("HUMIDITY_LOW", "MEDIUM", f"Humedad baja: {value:.1f} %")
    elif sensor_type == "door" and value >= 1:
        add("DOOR_OPEN", "HIGH", "Puerta abierta")
    elif sensor_type == "motion" and value >= 1:
        add("MOTION_DETECTED", "MEDIUM", "Movimiento detectado")

    return alerts


def alert_id(event_id: str, rule: str) -> str:
    return f"ALERT-{event_id}-{rule}"
