import logging
import os
import time

import paho.mqtt.client as mqtt
from simulator import Buffer, Simulator

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "warehouse")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "warehouse_pass")
WAREHOUSES = [w.strip() for w in os.getenv("WAREHOUSES", "WH-001,WH-002,WH-003").split(",") if w.strip()]
INTERVAL = float(os.getenv("INTERVAL_SECONDS", "5"))
DB_PATH = os.getenv("DB_PATH", "/data/simulator_buffer.db")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("iot.simulator")


def main():
    buffer = Buffer(DB_PATH)
    client = mqtt.Client(client_id=f"warehouse-simulator-{os.getpid()}")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            logger.info("mqtt_connected host=%s", MQTT_HOST)
            sent = buffer.flush(c)
            if sent:
                logger.info("buffer_flushed count=%s", sent)
        else:
            logger.error("mqtt_connect_failed rc=%s", rc)

    client.on_connect = on_connect
    simulator = Simulator(client, buffer, WAREHOUSES)
    connected = False

    while True:
        try:
            if not connected or not client.is_connected():
                client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
                client.loop_start()
                connected = True
            simulator.flush()
            sent = simulator.generate_once()
            logger.info("readings_sent=%s warehouses=%s", sent, len(WAREHOUSES))
        except Exception as exc:
            connected = False
            logger.warning("mqtt_error error=%s, se guarda en buffer", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
