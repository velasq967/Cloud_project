import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from central.config import settings
from central.database import SessionLocal, init_db
from central.messaging import publish_transfer
from central.models import Transfer, TransferHistory
from central.saga import REQUESTED, SIMULATIONS, TERMINAL

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("central.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Warehouse Central - Transferencias", lifespan=lifespan)


class TransferCreate(BaseModel):
    transfer_id: Optional[str] = Field(None, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    source_warehouse: str
    destination_warehouse: str
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0)
    simulate: Optional[str] = None


def next_id(db) -> str:
    numbers = [
        int(m.group(1))
        for (tid,) in db.query(Transfer.id).filter(Transfer.id.like("TR-%")).all()
        if (m := re.fullmatch(r"TR-(\d+)", tid))
    ]
    return f"TR-{(max(numbers) if numbers else 0) + 1:03d}"


def accepted(t: Transfer) -> dict:
    return {
        "transfer_id": t.id,
        "status": t.status if t.status in TERMINAL else "PROCESSING",
    }


@app.get("/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "central"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"db: {exc}")


@app.post("/transfers", status_code=status.HTTP_202_ACCEPTED)
def create_transfer(body: TransferCreate):
    whs = settings.warehouses
    if body.source_warehouse not in whs or body.destination_warehouse not in whs:
        raise HTTPException(status_code=400, detail=f"Bodegas validas: {', '.join(whs)}")
    if body.source_warehouse == body.destination_warehouse:
        raise HTTPException(status_code=400, detail="Origen y destino deben ser distintos.")
    if body.simulate and body.simulate not in SIMULATIONS:
        raise HTTPException(status_code=400, detail=f"simulate valido: {', '.join(sorted(SIMULATIONS))}")

    with SessionLocal() as db:
        if body.transfer_id:
            existing = db.get(Transfer, body.transfer_id)
            if existing:
                # mismo transfer_id = misma transferencia, no se crea otra
                logger.info("transfer_duplicated transfer_id=%s", existing.id)
                return accepted(existing)

        t = Transfer(
            id=body.transfer_id or next_id(db),
            source_warehouse=body.source_warehouse,
            destination_warehouse=body.destination_warehouse,
            sku=body.sku,
            quantity=body.quantity,
            status=REQUESTED,
            simulate=body.simulate,
            paused=False,
        )
        db.add(t)
        db.add(TransferHistory(transfer_id=t.id, status=REQUESTED, detail="solicitud recibida"))
        db.commit()

    publish_transfer(t.id)
    return accepted(t)


@app.get("/transfers")
def list_transfers(limit: int = 20):
    with SessionLocal() as db:
        rows = db.query(Transfer).order_by(Transfer.created_at.desc()).limit(limit).all()
        return [summary(t) for t in rows]


@app.get("/transfers/{transfer_id}")
def get_transfer(transfer_id: str):
    with SessionLocal() as db:
        t = db.get(Transfer, transfer_id)
        if not t:
            raise HTTPException(status_code=404, detail="Transferencia no encontrada.")
        history = (
            db.query(TransferHistory)
            .filter(TransferHistory.transfer_id == transfer_id)
            .order_by(TransferHistory.id)
            .all()
        )
        data = summary(t)
        data["history"] = [
            {"status": h.status, "detail": h.detail, "at": h.created_at.isoformat()} for h in history
        ]
        return data


@app.post("/transfers/{transfer_id}/resend", status_code=status.HTTP_202_ACCEPTED)
def resend(transfer_id: str):
    # solo para el experimento de mensaje duplicado: vuelve a mandar el mismo mensaje
    with SessionLocal() as db:
        t = db.get(Transfer, transfer_id)
        if not t:
            raise HTTPException(status_code=404, detail="Transferencia no encontrada.")
    published = publish_transfer(transfer_id)
    return {"transfer_id": transfer_id, "republished": published}


def summary(t: Transfer) -> dict:
    return {
        "transfer_id": t.id,
        "source_warehouse": t.source_warehouse,
        "destination_warehouse": t.destination_warehouse,
        "sku": t.sku,
        "quantity": t.quantity,
        "status": t.status,
        "simulate": t.simulate,
        "last_error": t.last_error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
