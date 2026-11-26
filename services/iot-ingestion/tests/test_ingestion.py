import pytest
from ingestion import build_iot_event, parse_topic, validate_reading


def payload(**overrides):
    base = {
        "event_id": "IOT-WH001-TEMP001-1",
        "warehouse_id": "WH-001",
        "sensor_id": "TEMP-001",
        "sensor_type": "temperature",
        "value": 8.4,
        "unit": "C",
        "sequence_number": 1,
        "occurred_at": "2026-11-25T10:00:00Z",
    }
    base.update(overrides)
    return base


def test_parse_topic():
    assert parse_topic("warehouses/WH-001/sensors/TEMP-001") == (
        "WH-001",
        "TEMP-001",
    )


def test_parse_topic_invalido():
    with pytest.raises(ValueError):
        parse_topic("warehouses/WH-001/TEMP-001")


def test_validate_reading_normaliza_tipos():
    reading = validate_reading(payload(value="8.4", sequence_number="7"), "WH-001", "TEMP-001")
    assert reading["value"] == 8.4
    assert reading["sequence_number"] == 7
    assert reading["warehouse_id"] == "WH-001"


def test_validate_rechaza_warehouse_del_topic_distinto():
    with pytest.raises(ValueError):
        validate_reading(payload(warehouse_id="WH-002"), "WH-001", "TEMP-001")


def test_build_event_usa_routing_key_de_la_bodega():
    reading = validate_reading(payload(), "WH-001", "TEMP-001")
    event, routing_key = build_iot_event(reading)
    assert event["event_type"] == "IOT_READING_RECEIVED"
    assert event["event_id"] == "IOT-WH001-TEMP001-1"
    assert routing_key == "warehouse.WH-001.IOT_READING_RECEIVED"
    assert event["payload"]["sensor_id"] == "TEMP-001"
