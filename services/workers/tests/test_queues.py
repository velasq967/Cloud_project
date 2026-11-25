from shared.rabbit import build_queues, dlq_name, queue_name


def test_queue_name_incluye_bodega():
    assert queue_name("cache.inventory", "WH-002") == "cache.inventory.WH-002.q"


def test_colas_de_una_bodega_no_escuchan_otras_bodegas():
    queues = build_queues("WH-001")
    routing_keys = [rk for rks in queues.values() for rk in rks]
    assert routing_keys, "debe haber bindings"
    assert all(rk.startswith("warehouse.WH-001.") for rk in routing_keys)
    assert not any("*" in rk for rk in routing_keys), "sin comodín de bodega"


def test_bodegas_distintas_tienen_colas_distintas():
    assert set(build_queues("WH-001")).isdisjoint(build_queues("WH-002"))


def test_dlq_por_cola():
    assert dlq_name("audit.events.WH-001.q") == "audit.events.WH-001.dlq"
    assert dlq_name("report.jobs.WH-002.q") == "report.jobs.WH-002.dlq"
