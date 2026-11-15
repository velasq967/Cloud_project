from warehouse_common.config import CommonSettings


class WarehouseSettings(CommonSettings):
    SERVICE_NAME: str = "warehouse-api"
    WAREHOUSE_ID: str = "WH-001"
    WAREHOUSE_NAME: str = "Bodega principal"
    DATABASE_URL: str = (
        "postgresql://warehouse_user:warehouse_pass@localhost:5433/warehouse_db"
    )
    SEED_ON_START: bool = False

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return [origin for origin in origins if origin]


settings = WarehouseSettings()
