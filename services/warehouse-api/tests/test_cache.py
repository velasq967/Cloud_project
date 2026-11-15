import fakeredis
import pytest
import redis
from app.cache import cache_client


class BrokenRedis:
    """Simula un Redis caído para probar la degradación graciosa."""

    def get(self, *args, **kwargs):
        raise redis.RedisError("redis down")

    def set(self, *args, **kwargs):
        raise redis.RedisError("redis down")

    def delete(self, *args, **kwargs):
        raise redis.RedisError("redis down")

    def ping(self, *args, **kwargs):
        raise redis.RedisError("redis down")


@pytest.fixture()
def cache_enabled():
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    cache_client._client = fake
    cache_client.enabled = True
    cache_client.ttl_seconds = 30
    fake.flushall()
    yield cache_client
    cache_client.enabled = False
    cache_client._client = None


def movement(client, product_id, movement_type, quantity):
    response = client.post(
        "/inventory/movements",
        json={
            "product_id": product_id,
            "type": movement_type,
            "quantity": quantity,
            "reference": "CACHE-TEST",
        },
    )
    assert response.status_code == 201, response.text
    return response


def test_first_read_is_database_and_second_is_cache(client, product, cache_enabled):
    movement(client, product["id"], "RECEIPT", 10)

    first = client.get(f"/inventory/{product['id']}")
    assert first.status_code == 200
    assert first.json()["source"] == "database"
    assert first.json()["quantity"] == 10

    second = client.get(f"/inventory/{product['id']}")
    assert second.status_code == 200
    assert second.json()["source"] == "cache"
    assert second.json()["quantity"] == 10


def test_movement_invalidates_cache(client, product, cache_enabled):
    movement(client, product["id"], "RECEIPT", 10)
    assert client.get(f"/inventory/{product['id']}").json()["source"] == "database"
    assert client.get(f"/inventory/{product['id']}").json()["source"] == "cache"

    movement(client, product["id"], "SHIPMENT", 4)

    after = client.get(f"/inventory/{product['id']}")
    assert after.status_code == 200
    assert after.json()["source"] == "database"
    assert after.json()["quantity"] == 6


def test_cache_is_disabled_by_default(client, product):
    movement(client, product["id"], "RECEIPT", 10)
    first = client.get(f"/inventory/{product['id']}")
    second = client.get(f"/inventory/{product['id']}")
    assert first.json()["source"] == "database"
    assert second.json()["source"] == "database"


def test_api_works_when_redis_is_down(client, product, cache_enabled):
    movement(client, product["id"], "RECEIPT", 10)
    cache_client._client = BrokenRedis()

    response = client.get(f"/inventory/{product['id']}")
    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["quantity"] == 10

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["redis"] == "down"


def test_metrics_endpoint_exposes_cache_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "warehouse_cache_hits_total" in response.text
    assert "warehouse_cache_misses_total" in response.text
