import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["System"])
logger = logging.getLogger("warehouse.health")


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health_check_database_failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "database": "down",
                "warehouse_id": settings.WAREHOUSE_ID,
            },
        )

    return {
        "status": "ok",
        "database": "ok",
        "warehouse_id": settings.WAREHOUSE_ID,
    }
