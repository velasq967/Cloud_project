from warehouse_common.config import CommonSettings


class WarehouseSettings(CommonSettings):
    SERVICE_NAME: str = "warehouse-api"
    WAREHOUSE_ID: str = "WH-001"
    WAREHOUSE_NAME: str = "Bodega principal"
    DATABASE_URL: str = (
        "postgresql://warehouse_user:warehouse_pass@localhost:5433/warehouse_db"
    )
    REDIS_URL: str = "redis://localhost:6380/0"
    CACHE_ENABLED: bool = False
    CACHE_TTL_SECONDS: int = 30
    RABBITMQ_ENABLED: bool = False
    RABBITMQ_URL: str = "amqp://warehouse:warehouse_pass@localhost:5672/%2F"
    RABBITMQ_EXCHANGE: str = "warehouse.events"
    SEED_ON_START: bool = False
    # permite simular demoras en los pasos de transferencia (fase 6)
    ALLOW_FAULT_INJECTION: bool = False

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return [origin for origin in origins if origin]


settings = WarehouseSettings()
