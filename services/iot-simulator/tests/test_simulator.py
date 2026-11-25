from simulator import Buffer, build_reading, topic_for


class FakeInfo:
    def __init__(self, rc=0):
        self.rc = rc


class FakeClient:
    def __init__(self, rc=0):
        self.rc = rc
        self.published = []

    def is_connected(self):
        return True

    def publish(self, topic, payload, qos=1):
        self.published.append((topic, payload))
        return FakeInfo(self.rc)


def test_build_reading_tiene_event_id_y_sequence():
    reading = build_reading("WH-001", "temperature", 8.4, sequence_number=150)
    assert reading["warehouse_id"] == "WH-001"
    assert reading["sensor_id"] == "TEMP-001"
    assert reading["sequence_number"] == 150
    assert reading["event_id"].startswith("IOT-WH-001-TEMP-001-150-")
    assert topic_for("WH-001", "TEMP-001") == "warehouses/WH-001/sensors/TEMP-001"


def test_buffer_guarda_y_reenvia(tmp_path):
    buffer = Buffer(str(tmp_path / "buffer.db"))
    buffer.add("warehouses/WH-001/sensors/TEMP-001", {"event_id": "E1"})
    buffer.add("warehouses/WH-001/sensors/HUM-001", {"event_id": "E2"})

    client = FakeClient()
    assert buffer.flush(client) == 2
    assert len(client.published) == 2
    assert buffer.pending() == []


def test_buffer_no_borra_si_falla_el_envio(tmp_path):
    buffer = Buffer(str(tmp_path / "buffer.db"))
    buffer.add("warehouses/WH-001/sensors/TEMP-001", {"event_id": "E1"})
    client = FakeClient(rc=1)
    assert buffer.flush(client) == 0
    assert len(buffer.pending()) == 1
