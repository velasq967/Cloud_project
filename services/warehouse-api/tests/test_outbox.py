from app.database import SessionLocal
from app.modules.outbox.models import OutboxEventEntity
from app.modules.outbox.service import OutboxService


def movement(client, product_id, quantity=10):
    response = client.post(
        "/inventory/movements",
        json={
            "product_id": product_id,
            "type": "RECEIPT",
            "quantity": quantity,
            "reference": "OUTBOX-TEST",
        },
    )
    assert response.status_code == 201, response.text


def test_movement_creates_outbox_events(client, product):
    movement(client, product["id"])

    with SessionLocal() as db:
        rows = db.query(OutboxEventEntity).order_by(OutboxEventEntity.id).all()
        assert len(rows) == 2
        assert {row.event_type for row in rows} == {
            "INVENTORY_MOVEMENT_REGISTERED",
            "INVENTORY_UPDATED",
        }
        assert all(row.event_id.startswith("EVT-") for row in rows)
        assert all(row.payload["payload"]["sku"] == product["sku"] for row in rows if row.event_type == "INVENTORY_UPDATED")


def test_publish_pending_marks_events_as_published(client, product, monkeypatch):
    movement(client, product["id"])

    with SessionLocal() as db:
        service = OutboxService(db)
        monkeypatch.setattr(
            "app.modules.outbox.service.publisher.publish_event",
            lambda event, routing_key: True,
        )
        published = service.publish_pending()
        assert published == 2
        rows = db.query(OutboxEventEntity).all()
        assert all(row.published_at is not None for row in rows)
        assert all(row.attempts == 2 for row in rows)


def test_publish_pending_leaves_events_pending_when_rabbit_fails(client, product, monkeypatch):
    movement(client, product["id"])

    with SessionLocal() as db:
        service = OutboxService(db)
        monkeypatch.setattr(
            "app.modules.outbox.service.publisher.publish_event",
            lambda event, routing_key: False,
        )
        published = service.publish_pending()
        assert published == 0
        rows = db.query(OutboxEventEntity).all()
        assert all(row.published_at is None for row in rows)
        assert all(row.last_error == "publish_failed" for row in rows)


def test_request_publica_solo_sus_eventos_en_una_conexion(client, product, monkeypatch):
    """Fase 10: el request no arrastra todo el atraso del outbox."""
    from app.publisher import publisher

    # 1. RabbitMQ caído: el primer movimiento deja 2 eventos pendientes
    movement(client, product["id"])

    # 2. RabbitMQ vuelve: el segundo movimiento solo publica sus 2 eventos
    llamadas = []

    def batch(items):
        llamadas.append(len(items))
        return len(items)

    monkeypatch.setattr(publisher, "publish_batch", batch)
    movement(client, product["id"])

    assert llamadas == [2], "una sola llamada (una conexión) con los 2 eventos del request"
    with SessionLocal() as db:
        rows = db.query(OutboxEventEntity).order_by(OutboxEventEntity.id).all()
        assert len(rows) == 4
        assert [r.published_at is not None for r in rows] == [False, False, True, True]


def test_publicacion_parcial_deja_el_resto_pendiente(client, product, monkeypatch):
    from app.publisher import publisher

    monkeypatch.setattr(publisher, "publish_batch", lambda items: 1)
    movement(client, product["id"])
    with SessionLocal() as db:
        rows = db.query(OutboxEventEntity).order_by(OutboxEventEntity.id).all()
        assert rows[0].published_at is not None
        assert rows[1].published_at is None
        assert rows[1].last_error == "publish_failed"
