import logging

from iot_logic import alert_id, evaluate_alerts, parse_reading
from shared.db import get_connection
from shared.logging import configure_worker_logging
from shared.rabbit import consume

configure_worker_logging("iot-alert-worker")
logger = logging.getLogger("worker.iot.alert")


def handle(event: dict) -> None:
    reading = parse_reading(event)
    alerts = evaluate_alerts(reading)
    if not alerts:
        return

    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            for item in alerts:
                cursor.execute(
                    """
                    INSERT INTO iot_alerts (
                        alert_id, warehouse_id, sensor_id, rule,
                        severity, message, value, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN')
                    ON CONFLICT (alert_id) DO NOTHING
                    """,
                    (
                        alert_id(reading["event_id"], item["rule"]),
                        reading["warehouse_id"],
                        reading["sensor_id"],
                        item["rule"],
                        item["severity"],
                        item["message"],
                        reading["value"],
                    ),
                )
                logger.warning(
                    "iot_alert_created alert_id=%s warehouse=%s sensor=%s rule=%s",
                    alert_id(reading["event_id"], item["rule"]),
                    reading["warehouse_id"],
                    reading["sensor_id"],
                    item["rule"],
                )
    finally:
        connection.close()


if __name__ == "__main__":
    consume("iot.alerts.q", handle, iot_only=True)
