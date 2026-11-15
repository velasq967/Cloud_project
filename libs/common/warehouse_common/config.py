from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    """Configuración común a todos los servicios.

    Cada servicio extiende esta clase y agrega sus propias variables.
    """

    APP_NAME: str = "Warehouse Cloud Platform"
    SERVICE_NAME: str = "service"
    ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
