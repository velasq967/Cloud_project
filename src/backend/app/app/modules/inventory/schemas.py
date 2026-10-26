from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MovementType(str, Enum):
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    ADJUSTMENT = "ADJUSTMENT"
    RESERVATION = "RESERVATION"
    RELEASE = "RELEASE"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    RETURN = "RETURN"


class MovementCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    type: MovementType
    quantity: int = Field(
        ...,
        gt=0,
        description="Siempre positivo. El tipo de movimiento define el efecto.",
    )
    reference: Optional[str] = Field(None, max_length=100)


class MovementResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: str
    type: str
    quantity: int
    reference: Optional[str]
    correlation_id: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryResponse(BaseModel):
    product_id: int
    warehouse_id: str
    quantity: int
    reserved_quantity: int
    available_quantity: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
