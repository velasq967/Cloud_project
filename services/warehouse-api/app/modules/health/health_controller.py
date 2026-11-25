import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cache import cache_client
from app.config import settings
from app.database import engine, get_db
from app.metrics import update_db_pool_metrics

router = APIRouter(tags=["System"])
logger = logging.getLogger("warehouse.health")


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    redis_status = cache_client.ping()

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health_check_database_failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "database": "down",
                "redis": redis_status,
                "warehouse_id": settings.WAREHOUSE_ID,
            },
        )

    # Redis caído no hace fallar la API: solo se pierde la caché.
    return {
        "status": "ok",
        "database": "ok",
        "redis": redis_status,
        "warehouse_id": settings.WAREHOUSE_ID,
    }


@router.get("/metrics", include_in_schema=False)
def metrics():
    update_db_pool_metrics(engine, settings.WAREHOUSE_ID)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
