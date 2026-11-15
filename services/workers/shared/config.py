from warehouse_common.config import CommonSettings


class WorkerSettings(CommonSettings):
    SERVICE_NAME: str = "worker"
    WAREHOUSE_ID: str = "WH-001"
    DATABASE_URL: str = (
        "postgresql://warehouse_user:warehouse_pass@localhost:5433/warehouse_db"
    )
    REDIS_URL: str = "redis://localhost:6380/0"
    RABBITMQ_URL: str = "amqp://warehouse:warehouse_pass@localhost:5672/%2F"
    RABBITMQ_EXCHANGE: str = "warehouse.events"


settings = WorkerSettings()
