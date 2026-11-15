from prometheus_client import Counter, Histogram

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
