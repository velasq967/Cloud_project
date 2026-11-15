from sqlalchemy import JSON, Column, DateTime, String, Text, func

from app.database import Base


class ReportJobEntity(Base):
    __tablename__ = "report_jobs"

    id = Column(String(36), primary_key=True)
    type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    requested_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    correlation_id = Column(String(100), nullable=True, index=True)
