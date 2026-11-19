"""Logica del read model de inventario global (fase 7).

Sin base de datos ni HTTP, para poder probarla con tests simples.
"""

from datetime import datetime, timezone


def parse_time(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_inventory_event(event: dict):
    """Convierte un evento INVENTORY_UPDATED en una fila del read model.
    Devuelve None si el evento no sirve (otro tipo, viejo sin sku, etc)."""
    if event.get("event_type") != "INVENTORY_UPDATED":
        return None
    payload = event.get("payload") or {}
    warehouse_id = payload.get("warehouse_id") or event.get("source")
    sku = payload.get("sku")
    if not warehouse_id or not sku:
        return None
    try:
        return {
            "warehouse_id": warehouse_id,
            "sku": sku,
            "quantity": int(payload["quantity"]),
            "reserved_quantity": int(payload.get("reserved_quantity") or 0),
            "last_event_id": event.get("event_id"),
            "last_event_at": parse_time(event["occurred_at"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def is_newer(current_at, incoming_at) -> bool:
    """Solo se aplica un evento si es mas nuevo que lo que ya hay.
    Asi un duplicado (misma fecha) o un evento que llega tarde no pisa un dato mas nuevo."""
    return current_at is None or incoming_at > current_at


def aggregate(sku, rows, in_transit=0, now=None):
    """Arma la respuesta de GET /global/inventory/{sku} a partir de las filas del read model."""
    now = now or datetime.now(timezone.utc)
    warehouses = []
    for r in sorted(rows, key=lambda x: x["warehouse_id"]):
        age = (now - parse_time(r["last_event_at"])).total_seconds()
        warehouses.append(
            {
                "warehouse_id": r["warehouse_id"],
                "quantity": r["quantity"],
                "reserved_quantity": r["reserved_quantity"],
                "available_quantity": r["quantity"] - r["reserved_quantity"],
                "last_update": parse_time(r["last_event_at"]).isoformat(),
                "age_seconds": round(age, 1),
                "projection_lag_ms": r.get("lag_ms"),
            }
        )
    total = sum(w["quantity"] for w in warehouses)
    reserved = sum(w["reserved_quantity"] for w in warehouses)
    return {
        "sku": sku,
        "source": "read_model",
        "total_quantity": total,
        "total_reserved": reserved,
        "total_available": total - reserved,
        "in_transit": in_transit,
        "warehouses": warehouses,
    }
