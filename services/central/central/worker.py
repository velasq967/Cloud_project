"""Worker que ejecuta la saga de transferencias.

- Consume TRANSFER_REQUESTED de RabbitMQ.
- Cada SWEEP_SECONDS revisa la tabla y retoma las transferencias que no han terminado
  (worker reiniciado, destino caido, mensaje perdido).
"""

import json
import logging
import signal
import sys
import time
import zlib

import pika
from pika.exceptions import AMQPError
from sqlalchemy import text

from central.client import WarehouseClient
from central.config import TRANSFER_QUEUE, settings
from central.database import SessionLocal, engine, init_db
from central.messaging import declare
from central.models import Transfer, TransferHistory
from central.saga import TERMINAL, Saga

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("central.worker")

client = WarehouseClient()


def process(transfer_id: str, origin: str) -> None:
    # lock por transferencia: si hay dos workers o llega el mensaje duplicado
    # mientras se procesa, solo uno la avanza
    key = zlib.crc32(transfer_id.encode())
    with engine.connect() as lock_conn:
        got = lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
        lock_conn.commit()
        if not got:
            logger.info("transfer_locked transfer_id=%s", transfer_id)
            return
        try:
            with SessionLocal() as db:
                t = db.get(Transfer, transfer_id)
                if not t:
                    logger.warning("transfer_not_found transfer_id=%s", transfer_id)
                    return
                if t.status in TERMINAL:
                    if origin == "message":
                        logger.info("duplicate_ignored transfer_id=%s status=%s", t.id, t.status)
                        db.add(
                            TransferHistory(
                                transfer_id=t.id,
                                status=t.status,
                                detail="mensaje duplicado ignorado, la transferencia ya termino",
                            )
                        )
                        db.commit()
                    return

                def save(tr, detail):
                    db.add(TransferHistory(transfer_id=tr.id, status=tr.status, detail=detail))
                    db.commit()
                    logger.info("transfer_state transfer_id=%s status=%s detail=%s", tr.id, tr.status, detail)

                saga = Saga(client, save, retries=settings.SAGA_RETRIES)
                saga.run(t)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            lock_conn.commit()


def sweep() -> None:
    with SessionLocal() as db:
        ids = [
            tid
            for (tid,) in db.query(Transfer.id)
            .filter(Transfer.status.notin_(TERMINAL))
            .order_by(Transfer.created_at)
            .all()
        ]
    for tid in ids:
        try:
            process(tid, "sweep")
        except Exception:
            logger.exception("sweep_failed transfer_id=%s", tid)


def stop(*_args):
    # docker stop / restart manda SIGTERM. Se sale de una vez: el estado ya esta guardado
    logger.info("worker_stopping")
    sys.exit(0)


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    init_db()
    logger.info("worker_starting")
    # al arrancar retoma lo que quedo a medias (ej: el worker se reinicio)
    sweep()
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
            channel = connection.channel()
            declare(channel)
            channel.basic_qos(prefetch_count=1)
            logger.info("worker_started queue=%s", TRANSFER_QUEUE)
            last_sweep = time.monotonic()
            for method, _props, body in channel.consume(TRANSFER_QUEUE, inactivity_timeout=1):
                if method is not None:
                    try:
                        transfer_id = json.loads(body)["transfer_id"]
                        process(transfer_id, "message")
                    except Exception:
                        # el estado esta en la base, el sweep lo vuelve a intentar
                        logger.exception("message_failed")
                    channel.basic_ack(method.delivery_tag)
                if time.monotonic() - last_sweep >= settings.SWEEP_SECONDS:
                    sweep()
                    last_sweep = time.monotonic()
        except AMQPError as exc:
            logger.warning("rabbitmq_error error=%s, reconectando", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
