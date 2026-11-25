from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc

from central.database import SessionLocal
from central.iot_models import IotAlert, SensorReading, SensorStat, SensorState

router = APIRouter(prefix="/iot", tags=["IoT"])


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def state_dict(row: SensorState) -> dict:
    return {
        "warehouse_id": row.warehouse_id,
        "sensor_id": row.sensor_id,
        "sensor_type": row.sensor_type,
        "value": row.value,
        "unit": row.unit,
        "sequence_number": row.last_sequence_number,
        "last_occurred_at": iso(row.last_occurred_at),
        "updated_at": iso(row.updated_at),
    }


def reading_dict(row: SensorReading) -> dict:
    return {
        "event_id": row.event_id,
        "warehouse_id": row.warehouse_id,
        "sensor_id": row.sensor_id,
        "sensor_type": row.sensor_type,
        "value": row.value,
        "unit": row.unit,
        "sequence_number": row.sequence_number,
        "occurred_at": iso(row.occurred_at),
        "received_at": iso(row.received_at),
    }


def alert_dict(row: IotAlert) -> dict:
    return {
        "alert_id": row.alert_id,
        "warehouse_id": row.warehouse_id,
        "sensor_id": row.sensor_id,
        "rule": row.rule,
        "severity": row.severity,
        "message": row.message,
        "value": row.value,
        "status": row.status,
        "created_at": iso(row.created_at),
    }


@router.get("/warehouses")
def iot_warehouses():
    with SessionLocal() as db:
        rows = db.query(SensorState).order_by(SensorState.warehouse_id).all()
    summary: dict[str, dict] = {}
    for row in rows:
        item = summary.setdefault(
            row.warehouse_id,
            {"warehouse_id": row.warehouse_id, "sensors": 0, "last_update": None},
        )
        item["sensors"] += 1
        updated = iso(row.updated_at)
        if updated and (not item["last_update"] or updated > item["last_update"]):
            item["last_update"] = updated
    return list(summary.values())


@router.get("/warehouses/{warehouse_id}/sensors")
def iot_warehouse_sensors(warehouse_id: str):
    with SessionLocal() as db:
        rows = (
            db.query(SensorState)
            .filter(SensorState.warehouse_id == warehouse_id)
            .order_by(SensorState.sensor_id)
            .all()
        )
    return [state_dict(row) for row in rows]


@router.get("/sensors/{sensor_id}/readings")
def iot_sensor_readings(
    sensor_id: str,
    warehouse_id: str | None = None,
    limit: int = 100,
):
    limit = max(1, min(limit, 500))
    with SessionLocal() as db:
        query = db.query(SensorReading).filter(SensorReading.sensor_id == sensor_id)
        if warehouse_id:
            query = query.filter(SensorReading.warehouse_id == warehouse_id)
        rows = (
            query.order_by(desc(SensorReading.occurred_at), desc(SensorReading.id))
            .limit(limit)
            .all()
        )
    return [reading_dict(row) for row in rows]


@router.get("/sensors/{sensor_id}/stats")
def iot_sensor_stats(sensor_id: str, warehouse_id: str | None = None):
    with SessionLocal() as db:
        query = db.query(SensorStat).filter(SensorStat.sensor_id == sensor_id)
        if warehouse_id:
            query = query.filter(SensorStat.warehouse_id == warehouse_id)
        rows = query.order_by(SensorStat.warehouse_id).all()
    return [
        {
            "warehouse_id": row.warehouse_id,
            "sensor_id": row.sensor_id,
            "sensor_type": row.sensor_type,
            "count": row.count,
            "min_value": row.min_value,
            "max_value": row.max_value,
            "avg_value": round(row.avg_value, 2),
            "last_value": row.last_value,
            "updated_at": iso(row.updated_at),
        }
        for row in rows
    ]


@router.get("/alerts")
def iot_alerts(status: str | None = None, limit: int = 50):
    limit = max(1, min(limit, 200))
    with SessionLocal() as db:
        query = db.query(IotAlert)
        if status:
            query = query.filter(IotAlert.status == status)
        rows = query.order_by(desc(IotAlert.created_at)).limit(limit).all()
    return [alert_dict(row) for row in rows]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str):
    with SessionLocal() as db:
        alert = db.query(IotAlert).filter(IotAlert.alert_id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alerta no encontrada.")
        alert.status = "ACKED"
        db.commit()
        return alert_dict(alert)


@router.get("/warehouses/{warehouse_id}/summary")
def iot_warehouse_summary(warehouse_id: str):
    with SessionLocal() as db:
        sensors = (
            db.query(SensorState)
            .filter(SensorState.warehouse_id == warehouse_id)
            .order_by(SensorState.sensor_id)
            .all()
        )
        alerts = (
            db.query(IotAlert)
            .filter(IotAlert.warehouse_id == warehouse_id, IotAlert.status == "OPEN")
            .order_by(desc(IotAlert.created_at))
            .limit(20)
            .all()
        )
        stats = (
            db.query(SensorStat)
            .filter(SensorStat.warehouse_id == warehouse_id)
            .order_by(SensorStat.sensor_id)
            .all()
        )
    return {
        "warehouse_id": warehouse_id,
        "sensors": [state_dict(row) for row in sensors],
        "open_alerts": [alert_dict(row) for row in alerts],
        "stats": [
            {
                "sensor_id": row.sensor_id,
                "sensor_type": row.sensor_type,
                "count": row.count,
                "min_value": row.min_value,
                "max_value": row.max_value,
                "avg_value": round(row.avg_value, 2),
            }
            for row in stats
        ],
    }
