"""GET /warehouses: estado de cada bodega."""

import asyncio

import httpx
from central.api import warehouses_status


def transport():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "wh1":
            return httpx.Response(200, json={"status": "ok", "database": "ok", "redis": "ok"})
        if host == "wh2":
            return httpx.Response(503, json={"status": "degraded", "database": "down", "redis": "ok"})
        raise httpx.ConnectError("sin conexion", request=request)

    return httpx.MockTransport(handler)


def test_estado_de_bodegas_no_falla_si_una_esta_caida():
    result = asyncio.run(
        warehouses_status(
            {"WH-001": "http://wh1", "WH-002": "http://wh2", "WH-003": "http://wh3"},
            transport=transport(),
        )
    )
    by_id = {r["warehouse_id"]: r for r in result}
    assert by_id["WH-001"]["status"] == "ok"
    assert by_id["WH-001"]["database"] == "ok"
    assert by_id["WH-001"]["redis"] == "ok"
    assert by_id["WH-002"]["status"] == "degraded"
    assert by_id["WH-002"]["database"] == "down"
    assert by_id["WH-003"]["status"] == "down"
    assert by_id["WH-003"]["error"] == "ConnectError"
