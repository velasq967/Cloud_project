FROM eclipse-mosquitto:2

COPY services/mosquitto/mosquitto.conf /mosquitto/config/mosquitto.conf
RUN mosquitto_passwd -c -b /mosquitto/config/passwd warehouse warehouse_pass \
    && chmod 644 /mosquitto/config/passwd
