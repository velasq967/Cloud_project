"""Fase 10: reintentos con espera, DLQ y errores que no se reintentan."""

import json
from types import SimpleNamespace

import psycopg2
import pytest
from shared import rabbit
from shared.rabbit import (
    MAX_ATTEMPTS,
    NonRetryableError,
    backoff_ms,
    decide,
    handle_delivery,
    retry_queue_name,
)

QUEUE = "audit.events.WH-001.q"


class FakeChannel:
    def __init__(self):
        self.published = []
        self.acks = []

    def basic_publish(self, exchange, routing_key, body, properties):
        self.published.append(
            {"exchange": exchange, "routing_key": routing_key, "body": body, "props": properties}
        )

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)


@pytest.fixture(autouse=True)
def sin_db(monkeypatch):
    procesados = set()
    monkeypatch.setattr(rabbit, "already_processed", lambda e, c: (e, c) in procesados)
    monkeypatch.setattr(rabbit, "mark_processed", lambda e, c: procesados.add((e, c)))
    return procesados


def deliver(handler, body=None, retry_count=0, on_dead_letter=None):
    ch = FakeChannel()
    if body is None:
        body = json.dumps({"event_id": "EVT-1", "event_type": "X", "correlation_id": "COR-1"}).encode()
    props = SimpleNamespace(
        headers={"x-retry-count": retry_count} if retry_count else None,
        correlation_id="COR-1",
        message_id="EVT-1",
        content_type="application/json",
    )
    result = handle_delivery(
        ch,
        SimpleNamespace(delivery_tag=7),
        props,
        body,
        queue=QUEUE,
        handler=handler,
        consumer_name="test",
        on_dead_letter=on_dead_letter,
    )
    return result, ch


def falla(exc):
    def handler(_event):
        raise exc

    return handler


def test_json_invalido_va_directo_a_dlq():
    result, ch = deliver(lambda e: None, body=b"{no es json")
    assert result == "dlq"
    assert ch.published[0]["routing_key"] == "audit.events.WH-001.dlq"
    assert ch.acks == [7]


def test_error_temporal_se_reintenta_sin_dormir_el_worker():
    result, ch = deliver(falla(psycopg2.OperationalError("db caida")))
    assert result == "retry"
    msg = ch.published[0]
    # va a la cola de espera, no a la principal, con TTL = backoff
    assert msg["routing_key"] == retry_queue_name(QUEUE) == "audit.events.WH-001.retry"
    assert msg["props"].expiration == "1000"
    assert msg["props"].headers["x-retry-count"] == 1
    # se conserva la trazabilidad
    assert msg["props"].correlation_id == "COR-1"
    assert msg["props"].message_id == "EVT-1"
    assert ch.acks == [7]


def test_tercer_intento_fallido_va_a_dlq():
    llamados = []
    result, ch = deliver(
        falla(TimeoutError("timeout")),
        retry_count=MAX_ATTEMPTS - 1,
        on_dead_letter=lambda e, r: llamados.append(r),
    )
    assert result == "dlq"
    msg = ch.published[0]
    assert msg["routing_key"] == "audit.events.WH-001.dlq"
    assert msg["props"].headers["x-attempts"] == MAX_ATTEMPTS
    assert "TimeoutError" in msg["props"].headers["x-error-reason"]
    assert llamados, "on_dead_letter debe avisar al worker"


def test_error_de_negocio_no_se_reintenta():
    result, ch = deliver(falla(NonRetryableError("producto no existe")))
    assert result == "dlq"
    assert ch.published[0]["routing_key"].endswith(".dlq")
    assert ch.published[0]["props"].headers["x-attempts"] == 1


def test_duplicado_no_ejecuta_el_handler(sin_db):
    sin_db.add(("EVT-1", "test"))
    llamados = []
    result, ch = deliver(lambda e: llamados.append(e))
    assert result == "duplicate"
    assert llamados == []
    assert ch.published == []


def test_exito_marca_el_evento_como_procesado(sin_db):
    result, ch = deliver(lambda e: None)
    assert result == "success"
    assert ("EVT-1", "test") in sin_db
    assert ch.published == []


@pytest.mark.parametrize(
    "exc, attempt, esperado",
    [
        (TimeoutError("t"), 1, "retry"),
        (TimeoutError("t"), MAX_ATTEMPTS, "dlq"),
        (psycopg2.OperationalError("db caida"), 2, "retry"),
        (psycopg2.IntegrityError("constraint"), 1, "dlq"),
        (NonRetryableError("no existe"), 1, "dlq"),
        (KeyError("payload"), 1, "dlq"),
    ],
)
def test_matriz_de_decision(exc, attempt, esperado):
    assert decide(attempt, exc) == esperado


def test_backoff_crece():
    assert [backoff_ms(i) for i in (1, 2, 3)] == [1000, 2000, 4000]
