import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text

from central.config import settings
from central.database import SessionLocal, init_db
from central.iot_api import router as iot_router
from central.messaging import publish_transfer
from central.models import Transfer, TransferHistory
from central.projection import aggregate
from central.read_model import all_skus, in_transit, rebuild, rows_for
from central.saga import REQUESTED, SIMULATIONS, TERMINAL

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("central.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Warehouse Central - Transferencias", lifespan=lifespan)

CENTRAL_REQUESTS = Counter(
    "central_http_requests_total",
    "Requests HTTP de la central",
    ["method", "path", "status"],
)
CENTRAL_LATENCY = Histogram(
    "central_http_request_duration_seconds",
    "Duración de requests de la central",
    ["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


@app.middleware("http")
async def central_metrics(request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    CENTRAL_REQUESTS.labels(
        method=request.method, path=path, status=str(response.status_code)
    ).inc()
    CENTRAL_LATENCY.labels(method=request.method, path=path).observe(
        time.perf_counter() - started
    )
    return response


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(iot_router)


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


async def check_warehouse(client: httpx.AsyncClient, wh: str, url: str) -> dict:
    """Llama al /health de una bodega. Nunca lanza: una bodega caida es un resultado."""
    started = time.perf_counter()
    try:
        r = await client.get(f"{url}/health")
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        detail = data.get("detail") if isinstance(data.get("detail"), dict) else data
        return {
            "warehouse_id": wh,
            "status": "ok" if r.status_code == 200 else "degraded",
            "http_status": r.status_code,
            "database": detail.get("database"),
            "redis": detail.get("redis"),
            "elapsed_ms": elapsed,
        }
    except httpx.TimeoutException:
        error = "timeout"
    except Exception as exc:
        error = exc.__class__.__name__
    return {
        "warehouse_id": wh,
        "status": "down",
        "http_status": None,
        "error": error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


async def warehouses_status(urls: dict[str, str], transport=None) -> list[dict]:
    async with httpx.AsyncClient(timeout=settings.LIVE_TIMEOUT, transport=transport) as client:
        return list(
            await asyncio.gather(*(check_warehouse(client, wh, url) for wh, url in urls.items()))
        )


@app.get("/warehouses")
async def list_warehouses():
    """Bodegas configuradas y su estado (consulta /health de cada una en paralelo)."""
    return await warehouses_status(settings.warehouses)


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


# ---------------- fase 7: inventario global ----------------


@app.get("/global/inventory")
def global_inventory_all(include_warehouses: bool = False):
    """Resumen de todos los sku desde el read model.
    Con include_warehouses=true trae el detalle por bodega."""
    with SessionLocal() as db:
        result = []
        for sku in all_skus(db):
            data = aggregate(sku, rows_for(db, sku), in_transit(db, sku))
            if not include_warehouses:
                del data["warehouses"]
            result.append(data)
        return result


@app.get("/global/inventory/{sku}")
def global_inventory(sku: str):
    """Alternativa B (CQRS): responde desde el read model, sin llamar a las bodegas."""
    started = time.perf_counter()
    with SessionLocal() as db:
        rows = rows_for(db, sku)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No hay datos de {sku} en el read model.")
        data = aggregate(sku, rows, in_transit(db, sku))
    data["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return data


async def _fetch_live(client, wh, url, sku):
    try:
        r = await client.get(f"{url}/internal/inventory", params={"sku": sku})
        r.raise_for_status()
        return wh, r.json(), None
    except httpx.TimeoutException:
        return wh, None, "timeout"
    except Exception as exc:
        return wh, None, f"{exc.__class__.__name__}"


@app.get("/global/inventory-live/{sku}")
async def global_inventory_live(sku: str):
    """Alternativa A: le pregunta a todas las bodegas en paralelo en cada request."""
    started = time.perf_counter()
    whs = settings.warehouses
    async with httpx.AsyncClient(timeout=settings.LIVE_TIMEOUT) as client:
        results = await asyncio.gather(*(_fetch_live(client, wh, url, sku) for wh, url in whs.items()))

    warehouses, errors = [], []
    for wh, items, error in results:
        if error:
            errors.append({"warehouse_id": wh, "error": error})
            continue
        for item in items:
            warehouses.append(
                {
                    "warehouse_id": wh,
                    "quantity": item["quantity"],
                    "reserved_quantity": item["reserved_quantity"],
                    "available_quantity": item["available_quantity"],
                }
            )
    if not warehouses and errors:
        raise HTTPException(status_code=503, detail={"sku": sku, "errors": errors})

    total = sum(w["quantity"] for w in warehouses)
    reserved = sum(w["reserved_quantity"] for w in warehouses)
    return {
        "sku": sku,
        "source": "live",
        "complete": not errors,
        "total_quantity": total,
        "total_reserved": reserved,
        "total_available": total - reserved,
        "warehouses": sorted(warehouses, key=lambda w: w["warehouse_id"]),
        "errors": errors,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@app.post("/global/rebuild")
def global_rebuild():
    """Reconstruye el read model con una foto del inventario de cada bodega."""
    with SessionLocal() as db:
        return {"result": rebuild(db)}
