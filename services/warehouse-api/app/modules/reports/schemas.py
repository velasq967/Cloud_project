from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    type: Literal["INVENTORY_SNAPSHOT", "MOVEMENTS_EXPORT"] = Field(
        "INVENTORY_SNAPSHOT",
        description="Tipo de reporte a generar.",
    )


class ReportJobResponse(BaseModel):
    job_id: str
    type: str
    status: str
    requested_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
