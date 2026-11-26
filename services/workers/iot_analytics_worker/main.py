import logging

from iot_logic import parse_reading
from shared.db import get_connection
from shared.logging import configure_worker_logging
from shared.rabbit import consume

configure_worker_logging("iot-analytics-worker")
logger = logging.getLogger("worker.iot.analytics")


def handle(event: dict) -> None:
    reading = parse_reading(event)
    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sensor_stats (
                    warehouse_id, sensor_id, sensor_type, count,
                    min_value, max_value, avg_value, last_value
                )
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s)
                ON CONFLICT (warehouse_id, sensor_id) DO UPDATE SET
                    sensor_type = EXCLUDED.sensor_type,
                    count = sensor_stats.count + 1,
                    min_value = LEAST(sensor_stats.min_value, EXCLUDED.last_value),
                    max_value = GREATEST(sensor_stats.max_value, EXCLUDED.last_value),
                    avg_value = (
                        (sensor_stats.avg_value * sensor_stats.count)
                        + EXCLUDED.last_value
                    ) / (sensor_stats.count + 1),
                    last_value = EXCLUDED.last_value,
                    updated_at = NOW()
                """,
                (
                    reading["warehouse_id"],
                    reading["sensor_id"],
                    reading["sensor_type"],
                    reading["value"],
                    reading["value"],
                    reading["value"],
                    reading["value"],
                ),
            )
        logger.info(
            "iot_stats_updated warehouse=%s sensor=%s value=%s",
            reading["warehouse_id"],
            reading["sensor_id"],
            reading["value"],
        )
    finally:
        connection.close()


if __name__ == "__main__":
    consume("iot.analytics.q", handle, iot_only=True)
