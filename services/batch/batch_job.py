import json
import os
from datetime import date, datetime, timezone

import boto3
import httpx

# Configuracion desde variables de entorno
WAREHOUSE_URLS = json.loads(
    os.getenv(
        "WAREHOUSE_URLS",
        '{"WH-001": "http://wh-001-api:8000", "WH-002": "http://wh-002-api:8000", "WH-003": "http://wh-003-api:8000"}',
    )
)
S3_BUCKET = os.getenv("S3_BUCKET", "warehouse-platform")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def get_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def upload_json(s3_client, key: str, payload: dict):
    """Sube un diccionario como JSON a S3. Al usar la misma key, es idempotente (sobrescribe)."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )


def normalize_inventory(items: list[dict]) -> list[dict]:
    """Normaliza la respuesta de /internal/inventory para el snapshot."""
    normalized = []
    for item in items:
        quantity = int(item.get("quantity") or 0)
        reserved = int(item.get("reserved_quantity") or 0)
        normalized.append(
            {
                "sku": item.get("sku"),
                "product_id": item.get("product_id"),
                "quantity": quantity,
                "reserved_quantity": reserved,
                "available_quantity": int(
                    item.get("available_quantity", quantity - reserved) or 0
                ),
                "updated_at": item.get("updated_at"),
            }
        )
    return sorted(normalized, key=lambda row: row["sku"] or "")


def build_snapshot(warehouse_id: str, target_date: str, items: list[dict]) -> dict:
    normalized = normalize_inventory(items)
    return {
        "warehouse_id": warehouse_id,
        "snapshot_date": target_date,
        "products_count": len(normalized),
        "items": normalized,
        "totals": {
            "quantity": sum(item["quantity"] for item in normalized),
            "reserved_quantity": sum(item["reserved_quantity"] for item in normalized),
            "available_quantity": sum(item["available_quantity"] for item in normalized),
        },
    }


def build_global_summary(snapshots: dict[str, dict]) -> dict:
    return {
        "total_warehouses_processed": len(snapshots),
        "total_products": sum(s["products_count"] for s in snapshots.values()),
        "total_units": sum(s["totals"]["quantity"] for s in snapshots.values()),
        "total_reserved": sum(
            s["totals"]["reserved_quantity"] for s in snapshots.values()
        ),
        "total_available": sum(
            s["totals"]["available_quantity"] for s in snapshots.values()
        ),
    }


def fetch_inventory(client: httpx.Client, base_url: str) -> list[dict]:
    """Consulta el endpoint interno que devuelve producto + inventario juntos."""
    response = client.get(f"{base_url}/internal/inventory")
    response.raise_for_status()
    return response.json()


def run_batch(
    run_date: str | None = None,
    s3_client=None,
    http_client: httpx.Client | None = None,
):
    target_date = run_date or date.today().isoformat()  # Ej: 2026-11-22
    year, month, _ = target_date.split("-")
    started_at = datetime.now(timezone.utc).isoformat()

    s3 = s3_client or get_s3_client()
    snapshots: dict[str, dict] = {}

    consolidated_report = {
        "report_date": target_date,
        "generated_at": started_at,
        "warehouses": {},
        "global_summary": {
            "total_warehouses_processed": 0,
            "total_products": 0,
            "total_units": 0,
            "total_reserved": 0,
            "total_available": 0,
        },
        "errors": [],
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=10.0)
    try:
        for wh_id, base_url in WAREHOUSE_URLS.items():
            try:
                items = fetch_inventory(client, base_url)
                snapshot = build_snapshot(wh_id, target_date, items)
                snapshots[wh_id] = snapshot

                # Guardar snapshot individual de la bodega
                wh_key = f"warehouses/{wh_id}/{year}/{month}/inventory-{target_date}.json"
                upload_json(s3, wh_key, snapshot)

                consolidated_report["warehouses"][wh_id] = {
                    "status": "OK",
                    "products_count": snapshot["products_count"],
                    "s3_snapshot_key": wh_key,
                    "totals": snapshot["totals"],
                }
            except Exception as exc:
                consolidated_report["errors"].append(
                    {"warehouse_id": wh_id, "error": str(exc)}
                )
    finally:
        if owns_client:
            client.close()

    consolidated_report["global_summary"] = build_global_summary(snapshots)

    # Guardar reporte consolidado en S3 (idempotente por fecha)
    report_key = f"reports/{year}/{month}/daily-summary-{target_date}.json"
    upload_json(s3, report_key, consolidated_report)

    # Registrar la ejecucion en la carpeta de auditoria
    audit_record = {
        "job": "daily_inventory_batch",
        "run_date": target_date,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETED_WITH_ERRORS" if consolidated_report["errors"] else "SUCCESS",
        "report_key": report_key,
        "errors_count": len(consolidated_report["errors"]),
    }
    audit_key = f"audit/batch-runs/{year}/{month}/run-{target_date}.json"
    upload_json(s3, audit_key, audit_record)

    print(
        f"[BATCH] Finalizado para {target_date}. "
        f"Reporte: s3://{S3_BUCKET}/{report_key}"
    )
    return audit_record


if __name__ == "__main__":
    run_batch(os.getenv("RUN_DATE"))
