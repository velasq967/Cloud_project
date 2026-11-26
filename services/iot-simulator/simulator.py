"""Simulador de sensores con buffer local para cortes de MQTT."""

import json
import random
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

SENSORS = {
    "temperature": {"sensor_id": "TEMP-001", "unit": "C", "min": 2.0, "max": 9.0},
    "humidity": {"sensor_id": "HUM-001", "unit": "%", "min": 30.0, "max": 75.0},
    "door": {"sensor_id": "DOOR-001", "unit": "bool", "min": 0.0, "max": 1.0},
    "motion": {"sensor_id": "MOTION-001", "unit": "bool", "min": 0.0, "max": 1.0},
}


def build_reading(
    warehouse_id: str,
    sensor_type: str,
    value: float,
    sequence_number: int | None = None,
    occurred_at: str | None = None,
) -> dict:
    spec = SENSORS[sensor_type]
    sequence = sequence_number or int(time.time() * 1000)
    return {
        "event_id": f"IOT-{warehouse_id}-{spec['sensor_id']}-{sequence}-{uuid.uuid4().hex[:8]}",
        "warehouse_id": warehouse_id,
        "sensor_id": spec["sensor_id"],
        "sensor_type": sensor_type,
        "value": round(float(value), 2),
        "unit": spec["unit"],
        "sequence_number": sequence,
        "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
    }


def random_value(sensor_type: str) -> float:
    spec = SENSORS[sensor_type]
    if sensor_type in ("door", "motion"):
        return 1.0 if random.random() < 0.25 else 0.0
    return random.uniform(spec["min"], spec["max"])


class Buffer:
    """Cola local SQLite para no perder lecturas si MQTT está caído."""

    def __init__(self, path: str):
        # check_same_thread=False: on_connect de paho corre en otro hilo.
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def add(self, topic: str, payload: dict) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO pending (topic, payload, created_at) VALUES (?, ?, ?)",
                (topic, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
            )
            self.connection.commit()

    def pending(self, limit: int = 100) -> list[tuple]:
        with self._lock:
            return self.connection.execute(
                "SELECT id, topic, payload FROM pending ORDER BY id LIMIT ?", (limit,)
            ).fetchall()

    def delete(self, row_id: int) -> None:
        with self._lock:
            self.connection.execute("DELETE FROM pending WHERE id = ?", (row_id,))
            self.connection.commit()

    def flush(self, client) -> int:
        sent = 0
        with self._lock:
            for row_id, topic, payload in self.pending():
                info = client.publish(topic, payload, qos=1)
                rc = getattr(info, "rc", info)
                if rc != 0:
                    break
                self.delete(row_id)
                sent += 1
        return sent


def topic_for(warehouse_id: str, sensor_id: str) -> str:
    return f"warehouses/{warehouse_id}/sensors/{sensor_id}"


class Simulator:
    def __init__(self, client, buffer: Buffer, warehouses: list[str]):
        self.client = client
        self.buffer = buffer
        self.warehouses = warehouses
        self.sequence = int(time.time() * 1000)

    def generate_once(self) -> int:
        self.sequence += 1
        count = 0
        for warehouse_id in self.warehouses:
            for sensor_type in SENSORS:
                reading = build_reading(
                    warehouse_id,
                    sensor_type,
                    random_value(sensor_type),
                    sequence_number=self.sequence,
                )
                topic = topic_for(warehouse_id, reading["sensor_id"])
                info = (
                    self.client.publish(topic, json.dumps(reading), qos=1)
                    if self.client.is_connected()
                    else None
                )
                if info is None or getattr(info, "rc", 0) != 0:
                    self.buffer.add(topic, reading)
                else:
                    count += 1
        return count

    def flush(self) -> int:
        return self.buffer.flush(self.client) if self.client.is_connected() else 0
