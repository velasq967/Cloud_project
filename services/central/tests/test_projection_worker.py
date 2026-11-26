"""Fase 10: el projection worker no entra en bucle con mensajes malos."""

import json
from types import SimpleNamespace

import pytest
from central.config import PROJECTION_DLQ, PROJECTION_MAX_ATTEMPTS, PROJECTION_RETRY_QUEUE
from central.projection_worker import InvalidEvent, decode, handle_delivery
from sqlalchemy.exc import OperationalError


class FakeChannel:
    def __init__(self):
        self.published = []
        self.acks = []
        self.nacks = []

    def basic_publish(self, exchange, routing_key, body, properties):
        self.published.append((routing_key, properties))

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue=True):
        self.nacks.append(delivery_tag)


def body(**payload):
    base = {"warehouse_id": "WH-001", "sku": "PROD-001", "quantity": 10, "reserved_quantity": 0}
    base.update(payload)
    return json.dumps(
        {
            "event_id": "EVT-1",
            "event_type": "INVENTORY_UPDATED",
            "occurred_at": "2026-11-19T10:00:00+00:00",
            "payload": base,
        }
    ).encode()


def run(raw, retry_count=0, apply_fn=lambda row: True):
    ch = FakeChannel()
    props = SimpleNamespace(headers={"x-retry-count": retry_count}, correlation_id="C", message_id="EVT-1")
    result = handle_delivery(ch, SimpleNamespace(delivery_tag=1), props, raw, apply_fn=apply_fn)
    return result, ch


def test_json_invalido_va_a_dlq_y_no_vuelve_a_la_cola():
    result, ch = run(b"{roto")
    assert result == "dlq"
    assert ch.published[0][0] == PROJECTION_DLQ
    assert ch.nacks == []  # antes: nack(requeue=True) -> bucle infinito
    assert ch.acks == [1]


def test_cantidad_invalida_va_a_dlq():
    with pytest.raises(InvalidEvent):
        decode(body(quantity="mucho"))
    result, ch = run(body(quantity="mucho"))
    assert result == "dlq"


def test_evento_de_otro_tipo_se_ignora():
    raw = json.dumps({"event_type": "INVENTORY_MOVEMENT_REGISTERED", "payload": {}}).encode()
    result, ch = run(raw)
    assert result == "ignored"
    assert ch.published == []


def test_db_caida_se_reintenta_con_espera():
    def caida(row):
        raise OperationalError("SELECT 1", {}, Exception("central-db caida"))

    result, ch = run(body(), apply_fn=caida)
    assert result == "retry"
    queue, props = ch.published[0]
    assert queue == PROJECTION_RETRY_QUEUE
    assert props.expiration == "1000"
    assert props.headers["x-retry-count"] == 1


def test_despues_del_ultimo_intento_va_a_dlq():
    def caida(row):
        raise OperationalError("SELECT 1", {}, Exception("central-db caida"))

    result, ch = run(body(), retry_count=PROJECTION_MAX_ATTEMPTS - 1, apply_fn=caida)
    assert result == "dlq"
    assert ch.published[0][0] == PROJECTION_DLQ


def test_evento_valido_se_aplica():
    aplicadas = []
    result, ch = run(body(), apply_fn=aplicadas.append)
    assert result == "applied"
    assert aplicadas[0]["sku"] == "PROD-001"
    assert "_event_id" in aplicadas[0]
