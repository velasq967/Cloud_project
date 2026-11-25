import logging
from datetime import datetime, timezone

from iot_logic import parse_reading
from shared.db import get_connection
from shared.logging import configure_worker_logging
from shared.rabbit import consume

configure_worker_logging("iot-storage-worker")
logger = logging.getLogger("worker.iot.storage")


def handle(event: dict) -> None:
    reading = parse_reading(event)
    if not reading.get("event_id"):
        raise ValueError("La lectura no tiene event_id")
    occurred_at = reading["occurred_at"] or datetime.now(timezone.utc)

    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            # Historial: un event_id se guarda una sola vez.
            cursor.execute(
                """
                INSERT INTO sensor_readings (
                    event_id, warehouse_id, sensor_id, sensor_type,
                    value, unit, sequence_number, occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    reading["event_id"],
                    reading["warehouse_id"],
                    reading["sensor_id"],
                    reading["sensor_type"],
                    reading["value"],
                    reading["unit"],
                    reading["sequence_number"],
                    occurred_at,
                ),
            )

            # Estado "último valor": solo avanza si la secuencia es mayor.
            cursor.execute(
                """
                INSERT INTO sensor_state (
                    warehouse_id, sensor_id, sensor_type, value, unit,
                    last_sequence_number, last_occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (warehouse_id, sensor_id) DO UPDATE SET
                    sensor_type = EXCLUDED.sensor_type,
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    last_sequence_number = EXCLUDED.last_sequence_number,
                    last_occurred_at = EXCLUDED.last_occurred_at,
                    updated_at = NOW()
                WHERE sensor_state.last_sequence_number < EXCLUDED.last_sequence_number
                """,
                (
                    reading["warehouse_id"],
                    reading["sensor_id"],
                    reading["sensor_type"],
                    reading["value"],
                    reading["unit"],
                    reading["sequence_number"],
                    occurred_at,
                ),
            )
        logger.info(
            "iot_reading_stored event_id=%s warehouse=%s sensor=%s seq=%s value=%s",
            reading["event_id"],
            reading["warehouse_id"],
            reading["sensor_id"],
            reading["sequence_number"],
            reading["value"],
        )
    finally:
        connection.close()


if __name__ == "__main__":
    consume("iot.storage.q", handle, iot_only=True)
