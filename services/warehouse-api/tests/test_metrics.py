def test_metrics_exposes_http_and_db_metrics(client):
    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text
    assert "warehouse_http_requests_total" in text
    assert "warehouse_http_request_duration_seconds" in text
    assert "warehouse_db_pool_checked_out" in text
    assert "warehouse_cache_hits_total" in text
