from pydantic_settings import BaseSettings, SettingsConfigDict


class CentralSettings(BaseSettings):
    SERVICE_NAME: str = "central"
    DATABASE_URL: str = "postgresql://warehouse_user:warehouse_pass@localhost:5450/central_db"
    RABBITMQ_URL: str = "amqp://warehouse:warehouse_pass@localhost:5672/%2F"
    RABBITMQ_EXCHANGE: str = "warehouse.events"
    # WH-001=http://wh001-api:8000,WH-002=http://wh002-lb
    WAREHOUSE_URLS: str = "WH-001=http://localhost:8001,WH-002=http://localhost:8002,WH-003=http://localhost:8003"
    REQUEST_TIMEOUT: float = 3.0
    SAGA_RETRIES: int = 3
    SWEEP_SECONDS: int = 5
    # timeout de la consulta en vivo a las bodegas (fase 7, alternativa A)
    LIVE_TIMEOUT: float = 2.0
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def warehouses(self) -> dict[str, str]:
        result = {}
        for item in self.WAREHOUSE_URLS.split(","):
            if "=" in item:
                wh, url = item.split("=", 1)
                result[wh.strip()] = url.strip().rstrip("/")
        return result


settings = CentralSettings()

TRANSFER_QUEUE = "transfers.saga.q"
TRANSFER_ROUTING_KEY = "transfer.TRANSFER_REQUESTED"

# fase 7: el projection worker escucha los INVENTORY_UPDATED de todas las bodegas
PROJECTION_QUEUE = "central.projection.q"
PROJECTION_ROUTING_KEY = "warehouse.*.INVENTORY_UPDATED"
# fase 10: reintentos con espera y DLQ del projection worker
PROJECTION_RETRY_QUEUE = "central.projection.retry"
PROJECTION_DLQ = "central.projection.dlq"
PROJECTION_MAX_ATTEMPTS = 5
