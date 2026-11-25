from iot_logic import alert_id, evaluate_alerts, parse_reading, should_update_state


def event(sensor_type="temperature", value=8.4, seq=10):
    return {
        "event_id": "EVT-IOT-1",
        "event_type": "IOT_READING_RECEIVED",
        "source": "WH-001",
        "occurred_at": "2026-11-25T10:00:00Z",
        "payload": {
            "warehouse_id": "WH-001",
            "sensor_id": "TEMP-001",
            "sensor_type": sensor_type,
            "value": value,
            "unit": "C",
            "sequence_number": seq,
            "occurred_at": "2026-11-25T10:00:00Z",
        },
    }


def test_parse_reading_normaliza():
    reading = parse_reading(event())
    assert reading["warehouse_id"] == "WH-001"
    assert reading["value"] == 8.4
    assert reading["sequence_number"] == 10


def test_temperatura_alta_genera_alerta():
    alerts = evaluate_alerts(parse_reading(event(value=9.5)))
    assert alerts[0]["rule"] == "TEMP_HIGH"
    assert alerts[0]["severity"] == "HIGH"


def test_temperatura_normal_no_genera_alerta():
    assert evaluate_alerts(parse_reading(event(value=5))) == []


def test_puerta_abierta_genera_alerta():
    alerts = evaluate_alerts(parse_reading(event("door", 1)))
    assert alerts[0]["rule"] == "DOOR_OPEN"


def test_solo_actualiza_estado_con_secuencia_mayor():
    assert should_update_state(None, 1)
    assert should_update_state(10, 11)
    assert not should_update_state(10, 10)
    assert not should_update_state(10, 9)


def test_alert_id_es_deterministico():
    assert alert_id("EVT-1", "TEMP_HIGH") == "ALERT-EVT-1-TEMP_HIGH"
