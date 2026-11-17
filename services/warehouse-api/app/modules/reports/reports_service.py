import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from warehouse_common.events import EventTypes

from app.config import settings
from app.correlation import get_correlation_id
from app.modules.reports.models import ReportJobEntity
from app.modules.reports.schemas import ReportCreate, ReportJobResponse
from app.publisher import publisher

logger = logging.getLogger("warehouse.reports")


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_response(job: ReportJobEntity) -> ReportJobResponse:
        return ReportJobResponse(
            job_id=job.id,
            type=job.type,
            status=job.status,
            requested_at=job.requested_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result=job.result,
            error=job.error,
        )

    def create_job(self, payload: ReportCreate) -> ReportJobResponse:
        job_id = str(uuid.uuid4())
        job = ReportJobEntity(
            id=job_id,
            type=payload.type,
            status="PENDING",
            correlation_id=get_correlation_id(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        publisher.publish(
            EventTypes.REPORT_REQUESTED,
            {
                "job_id": job_id,
                "report_type": payload.type,
                "warehouse_id": settings.WAREHOUSE_ID,
            },
            get_correlation_id(),
        )

        logger.info(
            "report_job_created",
            extra={
                "extra_fields": {
                    "job_id": job_id,
                    "report_type": payload.type,
                    "warehouse_id": settings.WAREHOUSE_ID,
                }
            },
        )
        return self._to_response(job)

    def get_job(self, job_id: str) -> ReportJobResponse:
        job = self.db.get(ReportJobEntity, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trabajo de reporte no encontrado.",
            )
        return self._to_response(job)
