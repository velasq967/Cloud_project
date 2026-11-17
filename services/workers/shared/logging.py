from warehouse_common.logging import configure_logging as _configure_logging

from shared.config import settings


def configure_worker_logging(service_name: str) -> None:
    _configure_logging(
        service_name=service_name,
        level=settings.LOG_LEVEL,
        warehouse_id=settings.WAREHOUSE_ID,
    )
