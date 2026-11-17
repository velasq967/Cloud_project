import logging

import redis
from shared.config import settings
from shared.logging import configure_worker_logging
from shared.rabbit import consume

configure_worker_logging("cache-worker")
logger = logging.getLogger("worker.cache")

QUEUE = "cache.inventory.q"
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def handle(event: dict) -> None:
    if event.get("event_type") != "INVENTORY_UPDATED":
        return

    payload = event.get("payload") or {}
    warehouse_id = payload.get("warehouse_id") or event.get("source")
    product_id = payload.get("product_id")
    key = f"warehouse:{warehouse_id}:inventory:{product_id}"

    redis_client.delete(key)
    logger.info(
        "cache_invalidated_async key=%s event_id=%s",
        key,
        event.get("event_id"),
    )


if __name__ == "__main__":
    consume(QUEUE, handle)
