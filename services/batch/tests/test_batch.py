from unittest.mock import MagicMock

import batch_job


def inventory(sku="PROD-001", quantity=100, reserved=10):
    return {
        "sku": sku,
        "product_id": 1,
        "quantity": quantity,
        "reserved_quantity": reserved,
        "available_quantity": quantity - reserved,
        "updated_at": "2026-11-24T10:00:00Z",
    }


def test_build_snapshot_incluye_cantidades_y_totales():
    snapshot = batch_job.build_snapshot(
        "WH-001",
        "2026-11-24",
        [inventory("PROD-002", 40, 0), inventory("PROD-001", 100, 10)],
    )
    assert snapshot["products_count"] == 2
    assert snapshot["items"][0]["sku"] == "PROD-001"
    assert snapshot["items"][0]["available_quantity"] == 90
    assert snapshot["totals"] == {
        "quantity": 140,
        "reserved_quantity": 10,
        "available_quantity": 130,
    }


def test_build_global_summary_suma_todas_las_bodegas():
    summary = batch_job.build_global_summary(
        {
            "WH-001": {
                "products_count": 2,
                "totals": {
                    "quantity": 140,
                    "reserved_quantity": 10,
                    "available_quantity": 130,
                },
            },
            "WH-002": {
                "products_count": 1,
                "totals": {
                    "quantity": 50,
                    "reserved_quantity": 0,
                    "available_quantity": 50,
                },
            },
        }
    )
    assert summary == {
        "total_warehouses_processed": 2,
        "total_products": 3,
        "total_units": 190,
        "total_reserved": 10,
        "total_available": 180,
    }


def test_run_batch_usa_internal_inventory_y_sube_snapshots(monkeypatch):
    responses = {
        "http://wh1": [inventory("PROD-001", 100, 10)],
        "http://wh2": [inventory("PROD-001", 50, 0)],
    }

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeClient:
        def get(self, url):
            base = url.removesuffix("/internal/inventory")
            return FakeResponse(responses[base])

        def close(self):
            return None

    s3 = MagicMock()
    monkeypatch.setattr(
        batch_job,
        "WAREHOUSE_URLS",
        {"WH-001": "http://wh1", "WH-002": "http://wh2"},
    )

    result = batch_job.run_batch(
        "2026-11-24",
        s3_client=s3,
        http_client=FakeClient(),
    )

    assert result["status"] == "SUCCESS"
    assert result["errors_count"] == 0
    assert s3.put_object.call_count == 4  # 2 snapshots + consolidado + auditoria

    uploaded_keys = [call.kwargs["Key"] for call in s3.put_object.call_args_list]
    assert "warehouses/WH-001/2026/11/inventory-2026-11-24.json" in uploaded_keys
    assert "reports/2026/11/daily-summary-2026-11-24.json" in uploaded_keys
    assert "audit/batch-runs/2026/11/run-2026-11-24.json" in uploaded_keys


def test_run_batch_continua_si_una_bodega_falla(monkeypatch):
    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeClient:
        def get(self, url):
            if "wh2" in url:
                raise RuntimeError("WH-002 caida")
            return FakeResponse([inventory()])

        def close(self):
            return None

    s3 = MagicMock()
    monkeypatch.setattr(
        batch_job,
        "WAREHOUSE_URLS",
        {"WH-001": "http://wh1", "WH-002": "http://wh2"},
    )

    result = batch_job.run_batch(
        "2026-11-24",
        s3_client=s3,
        http_client=FakeClient(),
    )

    assert result["status"] == "COMPLETED_WITH_ERRORS"
    assert result["errors_count"] == 1
