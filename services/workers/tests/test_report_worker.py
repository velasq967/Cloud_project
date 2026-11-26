"""Fase 10: el report worker ya no se traga los errores."""

import psycopg2
import pytest
from report_worker import main as report
from shared.rabbit import NonRetryableError


def evento(**payload):
    return {"event_id": "EVT-R", "payload": payload}


def test_sin_job_id_no_se_reintenta():
    with pytest.raises(NonRetryableError):
        report.handle(evento())


def test_tipo_desconocido_no_se_reintenta():
    with pytest.raises(NonRetryableError):
        report.handle(evento(job_id="J1", report_type="NO_EXISTE"))


def test_db_caida_se_relanza_para_reintentar(monkeypatch):
    def caida():
        raise psycopg2.OperationalError("db caida")

    monkeypatch.setattr(report, "get_connection", caida)
    with pytest.raises(psycopg2.OperationalError):
        report.handle(evento(job_id="J1"))


def test_en_dlq_el_job_queda_failed(monkeypatch):
    marcas = []
    monkeypatch.setattr(report, "_mark", lambda job_id, status, error, connection=None: marcas.append((job_id, status)))
    report.on_dead_letter(evento(job_id="J1"), "TimeoutError: t")
    assert marcas == [("J1", "FAILED")]
