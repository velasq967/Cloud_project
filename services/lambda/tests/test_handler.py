import json
from unittest.mock import MagicMock

import handler
import pytest


class Body:
    def __init__(self, content: str):
        self.content = content

    def read(self) -> bytes:
        return self.content.encode("utf-8")


def s3_event(key: str = "reports/2026/11/daily-summary-2026-11-24.json"):
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": key},
                }
            }
        ]
    }


def test_lambda_valida_y_genera_resumen():
    payload = {
        "report_date": "2026-11-24",
        "warehouses": {"WH-001": {"status": "OK"}},
        "global_summary": {"total_products": 3},
        "errors": [],
    }
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": Body(json.dumps(payload))}
    handler.s3 = fake_s3
    handler.sns = MagicMock()
    handler.SNS_TOPIC_ARN = ""

    result = handler.lambda_handler(s3_event(), None)

    assert result["statusCode"] == 200
    fake_s3.put_object.assert_called_once()
    assert fake_s3.put_object.call_args.kwargs["Key"] == (
        "exports/executive-summary-2026-11-24.json"
    )


def test_lambda_rechaza_json_invalido():
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": Body("{no es json")}
    handler.s3 = fake_s3

    with pytest.raises(ValueError):
        handler.lambda_handler(s3_event(), None)


def test_lambda_rechaza_reporte_incompleto():
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": Body('{"report_date":"2026-11-24"}')}
    handler.s3 = fake_s3

    with pytest.raises(ValueError):
        handler.lambda_handler(s3_event(), None)
