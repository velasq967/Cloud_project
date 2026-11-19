"""Logica de la saga de transferencias (fase 6).

No depende de la base de datos ni de HTTP, asi se puede probar con objetos falsos.
- client.call(warehouse_id, step, transfer, extra) llama a la bodega
- save(transfer, detail) guarda el estado y deja la linea en el historial
"""

import time
from datetime import datetime, timezone

REQUESTED = "REQUESTED"
RESERVING_SOURCE = "RESERVING_SOURCE"
SOURCE_RESERVED = "SOURCE_RESERVED"
IN_TRANSIT = "IN_TRANSIT"
DESTINATION_PENDING = "DESTINATION_PENDING"
DESTINATION_RECEIVED = "DESTINATION_RECEIVED"
COMPLETED = "COMPLETED"
COMPENSATING = "COMPENSATING"
RESERVATION_RELEASED = "RESERVATION_RELEASED"
FAILED = "FAILED"

TERMINAL = {COMPLETED, FAILED, RESERVATION_RELEASED}

# valores de "simulate" para los experimentos
SIMULATIONS = {
    "fail_before_reserve",
    "fail_after_reserve",
    "timeout",
    "pause_before_receive",
    "slow",
}


class BusinessError(Exception):
    """La bodega dijo que no (sin stock, producto no existe...). Reintentar no sirve."""


class TransientError(Exception):
    """Timeout, bodega caida o error 5xx. Puede funcionar si se reintenta."""


def utcnow():
    return datetime.now(timezone.utc)


class Saga:
    def __init__(
        self,
        client,
        save,
        retries=3,
        backoff=1.0,
        timeout_delay=5.0,
        pause_seconds=10.0,
        slow_seconds=4.0,
        sleep=time.sleep,
    ):
        self.client = client
        self.save = save
        self.retries = retries
        self.backoff = backoff
        self.timeout_delay = timeout_delay
        self.pause_seconds = pause_seconds
        self.slow_seconds = slow_seconds
        self.sleep = sleep

    def run(self, t):
        """Avanza la transferencia hasta un estado final o hasta que tenga que esperar."""
        while t.status not in TERMINAL:
            before = t.status
            handler = getattr(self, "_" + t.status.lower())
            handler(t)
            if t.status == before:
                # se quedo esperando (destino caido o compensacion pendiente),
                # el worker lo vuelve a intentar despues
                return t
        return t

    # -- helpers --

    def _move(self, t, status, detail):
        t.status = status
        t.last_error = None
        self.save(t, detail)
        if t.simulate == "slow" and status not in TERMINAL:
            self.sleep(self.slow_seconds)

    def _note(self, t, detail):
        t.last_error = detail
        self.save(t, detail)

    def _call(self, t, warehouse, step, extra_first=None):
        last = None
        for attempt in range(1, self.retries + 1):
            extra = extra_first if attempt == 1 else None
            try:
                return self.client.call(warehouse, step, t, extra)
            except TransientError as exc:
                last = exc
                self._note(t, f"{step} en {warehouse} intento {attempt} fallo: {exc}")
                if attempt < self.retries:
                    self.sleep(self.backoff * (2 ** (attempt - 1)))
        raise last

    # -- estados --

    def _requested(self, t):
        # antes de mover nada se revisa que el destino tenga el producto y responda
        try:
            self._call(t, t.destination_warehouse, "check")
        except BusinessError as exc:
            self._move(t, FAILED, f"destino no puede recibir: {exc}")
            return
        except TransientError as exc:
            self._move(t, FAILED, f"destino no responde, no se empieza la transferencia: {exc}")
            return
        self._move(t, RESERVING_SOURCE, "destino verificado, reservando en origen")

    def _reserving_source(self, t):
        if t.simulate == "fail_before_reserve":
            self._move(t, FAILED, "fallo simulado antes de reservar, no se toco el inventario")
            return

        extra = {"delay_seconds": self.timeout_delay} if t.simulate == "timeout" else None
        try:
            r = self._call(t, t.source_warehouse, "reserve", extra)
        except BusinessError as exc:
            self._move(t, FAILED, f"origen rechazo la reserva: {exc}")
            return
        except TransientError as exc:
            # no sabemos si la reserva alcanzo a quedar, toca compensar
            self._move(t, COMPENSATING, f"origen no respondio al reservar: {exc}")
            return
        detail = "reserva hecha en origen"
        if r.get("already_done"):
            detail += " (ya estaba hecha, respuesta repetida)"
        self._move(t, SOURCE_RESERVED, detail)

    def _source_reserved(self, t):
        if t.simulate == "fail_after_reserve":
            self._move(t, COMPENSATING, "fallo simulado despues de reservar")
            return
        try:
            self._call(t, t.source_warehouse, "dispatch")
        except (BusinessError, TransientError) as exc:
            self._move(t, COMPENSATING, f"no se pudo despachar desde origen: {exc}")
            return
        self._move(t, IN_TRANSIT, "mercancia despachada desde origen")

    def _in_transit(self, t):
        # despues de despachar ya no se compensa: la mercancia salio,
        # el paso de recibir se reintenta hasta que funcione
        if t.simulate == "pause_before_receive" and not t.paused:
            t.paused = True
            self._note(t, f"pausa simulada de {self.pause_seconds:.0f}s antes de recibir")
            self.sleep(self.pause_seconds)
        try:
            self._call(t, t.destination_warehouse, "receive")
        except (BusinessError, TransientError) as exc:
            t.pending_since = t.pending_since or utcnow()
            self._move(t, DESTINATION_PENDING, f"destino no recibio, se reintenta: {exc}")
            return
        self._move(t, DESTINATION_RECEIVED, "mercancia recibida en destino")

    def _destination_pending(self, t):
        try:
            self.client.call(t.destination_warehouse, "receive", t, None)
        except (BusinessError, TransientError) as exc:
            self._note(t, f"destino sigue sin recibir: {exc}")
            return
        self._move(t, DESTINATION_RECEIVED, "destino volvio y recibio la mercancia")

    def _destination_received(self, t):
        self._move(t, COMPLETED, "transferencia completada")

    def _compensating(self, t):
        try:
            r = self.client.call(t.source_warehouse, "cancel", t, None)
        except (BusinessError, TransientError) as exc:
            self._note(t, f"compensacion pendiente, origen no responde: {exc}")
            return
        result = r.get("result")
        if result == "already_dispatched":
            # el despacho si alcanzo a quedar, se sigue hacia adelante
            self._move(t, IN_TRANSIT, "el despacho si se habia hecho, se continua")
        elif result == "released":
            self._move(t, RESERVATION_RELEASED, "compensacion: reserva liberada en origen")
        else:
            self._move(t, RESERVATION_RELEASED, "compensacion: no habia reserva que liberar")
