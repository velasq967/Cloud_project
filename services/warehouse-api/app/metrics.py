from prometheus_client import Counter, Gauge, Histogram

CACHE_HITS = Counter(
    "warehouse_cache_hits_total",
    "Lecturas de inventario resueltas por Redis",
    ["warehouse_id"],
)

CACHE_MISSES = Counter(
    "warehouse_cache_misses_total",
    "Lecturas de inventario que no estaban en Redis",
    ["warehouse_id"],
)

CACHE_ERRORS = Counter(
    "warehouse_cache_errors_total",
    "Errores de comunicación con Redis",
    ["warehouse_id"],
)

CACHE_INVALIDATIONS = Counter(
    "warehouse_cache_invalidations_total",
    "Claves de inventario invalidadas",
    ["warehouse_id"],
)

INVENTORY_READ_LATENCY = Histogram(
    "warehouse_inventory_read_seconds",
    "Latencia de lectura de inventario",
    ["warehouse_id", "source"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

HTTP_REQUESTS = Counter(
    "warehouse_http_requests_total",
    "Requests HTTP por método, ruta y estado",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "warehouse_http_request_duration_seconds",
    "Duración de requests HTTP",
    ["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

HTTP_ERRORS = Counter(
    "warehouse_http_errors_total",
    "Requests HTTP con estado 5xx",
    ["method", "path"],
)

DB_POOL_CHECKED_OUT = Gauge(
    "warehouse_db_pool_checked_out",
    "Conexiones actualmente en uso del pool",
    ["warehouse_id"],
)

DB_POOL_SIZE = Gauge(
    "warehouse_db_pool_size",
    "Tamaño actual del pool de conexiones",
    ["warehouse_id"],
)

DB_POOL_OVERFLOW = Gauge(
    "warehouse_db_pool_overflow",
    "Conexiones extra por encima del pool base",
    ["warehouse_id"],
)


def update_db_pool_metrics(engine, warehouse_id: str) -> None:
    """Actualiza gauges del pool de SQLAlchemy antes de exponer /metrics."""
    try:
        pool = engine.pool
        DB_POOL_CHECKED_OUT.labels(warehouse_id=warehouse_id).set(pool.checkedout())
        DB_POOL_SIZE.labels(warehouse_id=warehouse_id).set(pool.size())
        DB_POOL_OVERFLOW.labels(warehouse_id=warehouse_id).set(pool.overflow())
    except Exception:
        # No romper /metrics si el pool no expone estas estadísticas.
        pass
