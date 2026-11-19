from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.transfers.schemas import TransferStepRequest, TransferStepResponse
from app.modules.transfers.transfers_service import TransferStepService

# endpoints que usa el orquestador de la saga (servicio central)
router = APIRouter(prefix="/internal/transfers", tags=["Transfers (internal)"])


@router.post("/{transfer_id}/{step}", response_model=TransferStepResponse)
def apply_step(
    transfer_id: str,
    step: str,
    payload: TransferStepRequest,
    db: Session = Depends(get_db),
):
    return TransferStepService(db).apply(transfer_id, step, payload)
