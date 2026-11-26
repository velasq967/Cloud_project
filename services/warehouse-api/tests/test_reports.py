def test_create_report_returns_pending_job(client):
    response = client.post("/reports", json={"type": "INVENTORY_SNAPSHOT"})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["type"] == "INVENTORY_SNAPSHOT"
    assert body["job_id"]


def test_get_report_job(client):
    created = client.post("/reports", json={"type": "MOVEMENTS_EXPORT"}).json()
    response = client.get(f"/reports/jobs/{created['job_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["job_id"]
    assert body["type"] == "MOVEMENTS_EXPORT"


def test_get_unknown_report_job_returns_404(client):
    response = client.get("/reports/jobs/no-existe")
    assert response.status_code == 404


def test_invalid_report_type_returns_422(client):
    response = client.post("/reports", json={"type": "NO_EXISTE"})
    assert response.status_code == 422


def test_report_queda_en_el_outbox_aunque_rabbit_este_caido(client):
    """Fase 10: antes el evento se perdía y el job quedaba PENDING para siempre."""
    from app.database import SessionLocal
    from app.modules.outbox.models import OutboxEventEntity

    created = client.post("/reports", json={"type": "INVENTORY_SNAPSHOT"}).json()
    with SessionLocal() as db:
        rows = db.query(OutboxEventEntity).filter_by(event_type="REPORT_REQUESTED").all()
        assert len(rows) == 1
        assert rows[0].published_at is None  # pendiente: lo publica el outbox worker
        assert rows[0].payload["payload"]["job_id"] == created["job_id"]
