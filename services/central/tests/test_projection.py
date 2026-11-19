from datetime import datetime, timedelta, timezone

from central.projection import aggregate, is_newer, parse_inventory_event


def evento(qty=100, reserved=0, at="2026-11-19T10:00:00+00:00", sku="PROD-001", wh="WH-001"):
    return {
        "event_id": "EVT-1",
        "event_type": "INVENTORY_UPDATED",
        "occurred_at": at,
        "source": wh,
        "payload": {"warehouse_id": wh, "product_id": 1, "sku": sku, "quantity": qty, "reserved_quantity": reserved},
    }


def test_parse_evento_valido():
    row = parse_inventory_event(evento(70, 5))
    assert row["warehouse_id"] == "WH-001"
    assert row["sku"] == "PROD-001"
    assert row["quantity"] == 70
    assert row["reserved_quantity"] == 5
    assert row["last_event_at"].tzinfo is not None


def test_ignora_otros_eventos():
    e = evento()
    e["event_type"] = "INVENTORY_MOVEMENT_REGISTERED"
    assert parse_inventory_event(e) is None


def test_ignora_eventos_viejos_sin_sku():
    e = evento()
    del e["payload"]["sku"]
    assert parse_inventory_event(e) is None


def test_evento_mas_nuevo_se_aplica():
    t = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)
    assert is_newer(None, t)
    assert is_newer(t, t + timedelta(seconds=1))


def test_duplicado_o_atrasado_no_se_aplica():
    t = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)
    assert not is_newer(t, t)
    assert not is_newer(t, t - timedelta(seconds=5))


def test_eventos_desordenados_queda_el_ultimo():
    estado = {}
    eventos = [
        evento(100, at="2026-11-19T10:00:00+00:00"),
        evento(70, at="2026-11-19T10:00:02+00:00"),
        evento(85, at="2026-11-19T10:00:01+00:00"),  # llega tarde
        evento(70, at="2026-11-19T10:00:02+00:00"),  # duplicado
    ]
    for e in eventos:
        row = parse_inventory_event(e)
        actual = estado.get("at")
        if is_newer(actual, row["last_event_at"]):
            estado = {"qty": row["quantity"], "at": row["last_event_at"]}
    assert estado["qty"] == 70


def test_aggregate_suma_las_bodegas():
    now = datetime(2026, 11, 19, 10, 0, 10, tzinfo=timezone.utc)
    rows = [
        {"warehouse_id": "WH-002", "quantity": 50, "reserved_quantity": 0, "last_event_at": "2026-11-19T10:00:00+00:00"},
        {"warehouse_id": "WH-001", "quantity": 100, "reserved_quantity": 10, "last_event_at": "2026-11-19T10:00:05+00:00"},
        {"warehouse_id": "WH-003", "quantity": 80, "reserved_quantity": 0, "last_event_at": "2026-11-19T10:00:00+00:00"},
    ]
    r = aggregate("PROD-001", rows, in_transit=30, now=now)
    assert r["total_quantity"] == 230
    assert r["total_reserved"] == 10
    assert r["total_available"] == 220
    assert r["in_transit"] == 30
    assert [w["warehouse_id"] for w in r["warehouses"]] == ["WH-001", "WH-002", "WH-003"]
    assert r["warehouses"][0]["age_seconds"] == 5.0


def test_aggregate_sin_datos():
    r = aggregate("NADA", [])
    assert r["total_quantity"] == 0
    assert r["warehouses"] == []
