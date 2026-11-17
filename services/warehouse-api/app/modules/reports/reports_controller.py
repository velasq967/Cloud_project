from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.reports.reports_service import ReportService
from app.modules.reports.schemas import ReportCreate, ReportJobResponse

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post(
    "",
    response_model=ReportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    return ReportService(db).create_job(payload)


@router.get("/jobs/{job_id}", response_model=ReportJobResponse)
def get_report_job(job_id: str, db: Session = Depends(get_db)):
    return ReportService(db).get_job(job_id)
