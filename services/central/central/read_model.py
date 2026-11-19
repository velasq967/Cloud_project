from datetime import datetime, timezone

import httpx
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from central.config import settings
from central.models import GlobalInventory, Transfer
from central.projection import parse_time
from central.saga import DESTINATION_PENDING, IN_TRANSIT


def upsert(db, row: dict) -> bool:
    """Guarda la fila solo si es mas nueva que la que hay (idempotente y tolera desorden).
    Devuelve True si se aplico."""
    now = datetime.now(timezone.utc)
    lag_ms = int((now - parse_time(row["last_event_at"])).total_seconds() * 1000)
    stmt = insert(GlobalInventory).values(**row, projected_at=now, lag_ms=max(lag_ms, 0))
    stmt = stmt.on_conflict_do_update(
        index_elements=["warehouse_id", "sku"],
        set_={
            "quantity": stmt.excluded.quantity,
            "reserved_quantity": stmt.excluded.reserved_quantity,
            "last_event_id": stmt.excluded.last_event_id,
            "last_event_at": stmt.excluded.last_event_at,
            "projected_at": stmt.excluded.projected_at,
            "lag_ms": stmt.excluded.lag_ms,
        },
        where=GlobalInventory.last_event_at < stmt.excluded.last_event_at,
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount > 0


def rows_for(db, sku: str) -> list[dict]:
    return [
        {
            "warehouse_id": r.warehouse_id,
            "quantity": r.quantity,
            "reserved_quantity": r.reserved_quantity,
            "last_event_at": r.last_event_at,
            "lag_ms": r.lag_ms,
        }
        for r in db.query(GlobalInventory).filter(GlobalInventory.sku == sku).all()
    ]


def in_transit(db, sku: str) -> int:
    # unidades que ya salieron del origen pero no han llegado (fase 6)
    total = (
        db.query(func.coalesce(func.sum(Transfer.quantity), 0))
        .filter(Transfer.sku == sku, Transfer.status.in_([IN_TRANSIT, DESTINATION_PENDING]))
        .scalar()
    )
    return int(total or 0)


def all_skus(db) -> list[str]:
    return [s for (s,) in db.query(GlobalInventory.sku).distinct().order_by(GlobalInventory.sku)]


def rebuild(db) -> dict:
    """Reconstruye el read model pidiendo una foto del inventario a cada bodega.
    Se usa al arrancar (el stock inicial no genera eventos) o si el read model se pierde."""
    result = {}
    with httpx.Client(timeout=3.0) as client:
        for wh, url in settings.warehouses.items():
            # la hora se toma antes de pedir la foto: cualquier evento posterior la reemplaza
            taken_at = datetime.now(timezone.utc)
            try:
                r = client.get(f"{url}/internal/inventory")
                r.raise_for_status()
                items = r.json()
            except Exception as exc:
                result[wh] = f"error: {exc.__class__.__name__}"
                continue
            applied = 0
            for item in items:
                applied += upsert(
                    db,
                    {
                        "warehouse_id": wh,
                        "sku": item["sku"],
                        "quantity": item["quantity"],
                        "reserved_quantity": item["reserved_quantity"],
                        "last_event_id": "snapshot",
                        "last_event_at": taken_at,
                    },
                )
            result[wh] = f"ok ({len(items)} productos, {applied} actualizados)"
    return result
