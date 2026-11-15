from warehouse_common.logging import configure_logging as _configure_logging

from app.config import settings


def configure_logging() -> None:
    _configure_logging(
        service_name=settings.SERVICE_NAME,
        level=settings.LOG_LEVEL,
        warehouse_id=settings.WAREHOUSE_ID,
    )
