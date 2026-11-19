from typing import Optional

from pydantic import BaseModel, Field


class TransferStepRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0)
    # solo para los experimentos: espera despues de aplicar el paso
    delay_seconds: float = Field(0, ge=0, le=15)


class TransferStepResponse(BaseModel):
    transfer_id: str
    step: str
    warehouse_id: str
    result: str
    already_done: bool = False
    quantity: Optional[int] = None
    reserved_quantity: Optional[int] = None
