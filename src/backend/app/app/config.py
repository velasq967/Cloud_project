from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Warehouse Cloud Platform"
    WAREHOUSE_ID: str = "WH-001"
    DATABASE_URL: str = (
        "postgresql://warehouse_user:warehouse_pass@localhost:5433/warehouse_db"
    )
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
