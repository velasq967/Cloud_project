import json
import logging
from typing import Any

import redis

from app.config import settings
from app.metrics import (
    CACHE_ERRORS,
    CACHE_HITS,
    CACHE_INVALIDATIONS,
    CACHE_MISSES,
)

logger = logging.getLogger("warehouse.cache")


class CacheClient:
    """Cliente Redis con degradación graciosa.

    Si Redis no está disponible, la API debe seguir funcionando contra
    PostgreSQL. Por eso todos los métodos capturan errores de Redis y
    devuelven un valor seguro (None / False) en vez de propagar la excepción.
    """

    def __init__(
        self,
        url: str,
        warehouse_id: str,
        enabled: bool,
        ttl_seconds: int,
    ) -> None:
        self.url = url
        self.warehouse_id = warehouse_id
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        return self._client

    def inventory_key(self, product_id: int) -> str:
        return f"warehouse:{self.warehouse_id}:inventory:{product_id}"

    def get_json(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            raw = self.client.get(key)
        except redis.RedisError as exc:
            CACHE_ERRORS.labels(warehouse_id=self.warehouse_id).inc()
            logger.warning("cache_get_failed key=%s error=%s", key, exc)
            return None

        if raw is None:
            CACHE_MISSES.labels(warehouse_id=self.warehouse_id).inc()
            return None

        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            CACHE_ERRORS.labels(warehouse_id=self.warehouse_id).inc()
            logger.warning("cache_value_invalid key=%s", key)
            return None

        CACHE_HITS.labels(warehouse_id=self.warehouse_id).inc()
        return value

    def set_json(self, key: str, value: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            self.client.set(key, json.dumps(value), ex=self.ttl_seconds)
            return True
        except redis.RedisError as exc:
            CACHE_ERRORS.labels(warehouse_id=self.warehouse_id).inc()
            logger.warning("cache_set_failed key=%s error=%s", key, exc)
            return False

    def delete_inventory(self, product_id: int) -> bool:
        if not self.enabled:
            return False
        key = self.inventory_key(product_id)
        try:
            self.client.delete(key)
            CACHE_INVALIDATIONS.labels(warehouse_id=self.warehouse_id).inc()
            return True
        except redis.RedisError as exc:
            CACHE_ERRORS.labels(warehouse_id=self.warehouse_id).inc()
            logger.warning("cache_delete_failed key=%s error=%s", key, exc)
            return False

    def ping(self) -> str:
        if not self.enabled:
            return "disabled"
        try:
            return "ok" if self.client.ping() else "down"
        except redis.RedisError as exc:
            logger.warning("cache_ping_failed error=%s", exc)
            return "down"


cache_client = CacheClient(
    url=settings.REDIS_URL,
    warehouse_id=settings.WAREHOUSE_ID,
    enabled=settings.CACHE_ENABLED,
    ttl_seconds=settings.CACHE_TTL_SECONDS,
)
