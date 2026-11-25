import json
import logging
import os
import time

import paho.mqtt.client as mqtt
import pika
from ingestion import build_iot_event, parse_topic, validate_reading
from warehouse_common.logging import configure_logging

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "warehouse")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "warehouse_pass")
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", "amqp://warehouse:warehouse_pass@rabbitmq:5672/%2F"
)
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "warehouse.events")

configure_logging("iot-ingestion", os.getenv("LOG_LEVEL", "INFO"), "IOT")
logger = logging.getLogger("iot.ingestion")


class RabbitPublisher:
    def __init__(self):
        self.connection = None
        self.channel = None

    def _connect(self):
        parameters = pika.URLParameters(RABBITMQ_URL)
        parameters.connection_attempts = 1
        parameters.retry_delay = 0
        parameters.socket_timeout = 2
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(
            exchange=RABBITMQ_EXCHANGE,
            exchange_type="topic",
            durable=True,
        )

    def publish(self, event: dict, routing_key: str) -> None:
        try:
            if self.connection is None or self.connection.is_closed:
                self._connect()
            self.channel.basic_publish(
                exchange=RABBITMQ_EXCHANGE,
                routing_key=routing_key,
                body=json.dumps(event).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    correlation_id=event.get("correlation_id"),
                    message_id=event.get("event_id"),
                ),
            )
        except Exception:
            self.close()
            raise

    def close(self):
        if self.connection is not None and self.connection.is_open:
            self.connection.close()
        self.connection = None
        self.channel = None


publisher = RabbitPublisher()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("mqtt_connected host=%s", MQTT_HOST)
        client.subscribe("warehouses/+/sensors/+", qos=1)
    else:
        logger.error("mqtt_connect_failed rc=%s", rc)


def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        warehouse_id, sensor_id = parse_topic(message.topic)
        reading = validate_reading(payload, warehouse_id, sensor_id)
        event, routing_key = build_iot_event(reading)
        publisher.publish(event, routing_key)
        logger.info(
            "iot_reading_published event_id=%s warehouse=%s sensor=%s seq=%s",
            reading["event_id"],
            warehouse_id,
            sensor_id,
            reading["sequence_number"],
        )
    except Exception:
        logger.exception("iot_message_failed topic=%s", message.topic)


def run():
    client = mqtt.Client(client_id="iot-ingestion")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            client.loop_forever()
        except Exception as exc:
            logger.warning("mqtt_loop_failed error=%s, reintentando", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
