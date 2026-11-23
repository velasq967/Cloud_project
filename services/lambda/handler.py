import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client("s3")
sns = boto3.client("sns")

# Opcional: si creas un tópico SNS en AWS, pon su ARN en las variables de entorno de la Lambda
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")


def log_json(level: str, event: str, **details):
    """Paso 3 (Registrar): Imprime logs estructurados que AWS guarda automáticamente en CloudWatch."""
    record = {
        "service": "report-processor-lambda",
        "level": level,
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    print(json.dumps(record))


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        log_json("INFO", "s3_object_received", bucket=bucket, key=key)

        #aqui se lee el archivo json que se subio al bucket de s3
        response = s3.get_object(Bucket=bucket, Key=key)
        raw_content = response["Body"].read().decode("utf-8")

        #revisa que el json sea valido
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            log_json("ERROR", "validation_failed", key=key, reason=f"JSON inválido: {exc}")
            raise ValueError(f"Archivo {key} no es un JSON válido")

        if "report_date" not in data or "warehouses" not in data:
            log_json("ERROR", "validation_failed", key=key, reason="Faltan campos report_date o warehouses")
            raise ValueError(f"Archivo {key} incompleto")

        log_json("INFO", "report_validated", key=key, report_date=data["report_date"])

        #crear un resumen ejecutivo limpio y guardarlo en exports/
        summary = {
            "report_date": data["report_date"],
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "source_file": key,
            "warehouses_ok": len(data.get("warehouses", {})),
            "warehouses_with_errors": len(data.get("errors", [])),
            "total_products": data.get("global_summary", {}).get("total_products", 0),
        }

        export_key = f"exports/executive-summary-{data['report_date']}.json"
        s3.put_object(
            Bucket=bucket,
            Key=export_key,
            Body=json.dumps(summary, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        #dejar constancia en CloudWatch
        log_json("INFO", "report_transformed_and_saved", export_key=export_key, summary=summary)

        #avisar al resto del sistema vía SNS
        domain_event = {
            "event_type": "report.processed",
            "report_date": data["report_date"],
            "export_key": export_key,
            "bucket": bucket,
        }

        if SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"Reporte diario procesado: {data['report_date']}",
                Message=json.dumps(domain_event),
            )
            log_json("INFO", "event_published_sns", topic=SNS_TOPIC_ARN, domain_event=domain_event)
        else:
            log_json("INFO", "event_published_simulated", domain_event=domain_event)

    return {"statusCode": 200, "body": json.dumps({"status": "processed"})}