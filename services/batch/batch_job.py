import json
import os
from datetime import date, datetime, timezone
import boto3
import httpx

# Configuración desde variables de entorno
WAREHOUSE_URLS = json.loads(
    os.getenv(
        "WAREHOUSE_URLS",
        '{"WH-001": "http://wh-001-api:8000", "WH-002": "http://wh-002-api:8000", "WH-003": "http://wh-003-api:8000"}',
    )
)
S3_BUCKET = os.getenv("S3_BUCKET", "warehouse-platform")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def get_s3_client():
    return boto3.client("s3",region_name=AWS_REGION)


def upload_json(s3_client, key: str, payload: dict):
    """Sube un diccionario como JSON a S3. Al usar la misma key, es idempotente (sobrescribe)."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )


def run_batch(run_date: str | None = None):
    target_date = run_date or date.today().isoformat()  # Ej: 2026-11-22
    year, month, _ = target_date.split("-")
    started_at = datetime.now(timezone.utc).isoformat()

    s3 = get_s3_client()

    consolidated_report = {
        "report_date": target_date,
        "generated_at": started_at,
        "warehouses": {},
        "global_summary": {
            "total_warehouses_processed": 0,
            "total_products": 0,
            "total_units": 0,
        },
        "errors": [],
    }

    # 1. Recorrer cada bodega de forma independiente
    with httpx.Client(timeout=10.0) as client:
        for wh_id, base_url in WAREHOUSE_URLS.items():
            try:
                # Consultamos productos (ajusta el endpoint si tu API usa otro prefijo)
                resp = client.get(f"{base_url}/products")
                resp.raise_for_status()
                products = resp.json()

                wh_snapshot = {
                    "warehouse_id": wh_id,
                    "snapshot_date": target_date,
                    "products_count": len(products),
                    "items": products,
                }

                # 2. Guardar snapshot individual de la bodega en la ruta sugerida por la guía
                wh_key = f"warehouses/{wh_id}/{year}/{month}/inventory-{target_date}.json"
                upload_json(s3, wh_key, wh_snapshot)

                consolidated_report["warehouses"][wh_id] = {
                    "status": "OK",
                    "products_count": len(products),
                    "s3_snapshot_key": wh_key,
                }
                consolidated_report["global_summary"]["total_warehouses_processed"] += 1
                consolidated_report["global_summary"]["total_products"] += len(products)

            except Exception as exc:
                consolidated_report["errors"].append(
                    {"warehouse_id": wh_id, "error": str(exc)}
                )

    # 3. Guardar reporte consolidado en S3 (idempotente por fecha)
    report_key = f"reports/{year}/{month}/daily-summary-{target_date}.json"
    upload_json(s3, report_key, consolidated_report)

    # 4. Registrar la ejecución en la carpeta de auditoría
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

    print(f"[BATCH] Finalizado para {target_date}. Reporte: s3://{S3_BUCKET}/{report_key}")
    return audit_record


if __name__ == "__main__":
    run_batch(os.getenv("RUN_DATE"))