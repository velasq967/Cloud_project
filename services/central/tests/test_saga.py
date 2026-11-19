from central.saga import (
    COMPENSATING,
    COMPLETED,
    DESTINATION_PENDING,
    FAILED,
    REQUESTED,
    RESERVATION_RELEASED,
    BusinessError,
    Saga,
    TransientError,
)


class T:
    def __init__(self, simulate=None, quantity=30):
        self.id = "TR-001"
        self.source_warehouse = "WH-001"
        self.destination_warehouse = "WH-002"
        self.sku = "PROD-001"
        self.quantity = quantity
        self.status = REQUESTED
        self.simulate = simulate
        self.last_error = None
        self.pending_since = None
        self.paused = False


class FakeWarehouse:
    """Imita los endpoints idempotentes de una bodega."""

    def __init__(self, quantity=100):
        self.quantity = quantity
        self.reserved = 0
        self.ops = {}
        self.down = False
        self.lost_responses = 0  # aplica el paso pero la respuesta "se pierde"

    def apply(self, tid, step, q):
        if self.down:
            raise TransientError("bodega caida")
        if step == "check":
            return {"result": "ok"}
        if (tid, step) in self.ops:
            return {"result": self.ops[(tid, step)], "already_done": True}
        cancelled = (tid, "cancel") in self.ops
        if step == "reserve":
            if cancelled:
                raise BusinessError("cancelada")
            if self.quantity - self.reserved < q:
                raise BusinessError("sin stock")
            self.reserved += q
            result = "reserved"
        elif step == "dispatch":
            if cancelled or (tid, "reserve") not in self.ops:
                raise BusinessError("no se puede despachar")
            self.reserved -= q
            self.quantity -= q
            result = "dispatched"
        elif step == "receive":
            self.quantity += q
            result = "received"
        else:  # cancel
            if (tid, "dispatch") in self.ops:
                return {"result": "already_dispatched"}
            if (tid, "reserve") in self.ops:
                self.reserved -= q
                result = "released"
            else:
                result = "nothing_reserved"
        self.ops[(tid, step)] = result
        if self.lost_responses:
            self.lost_responses -= 1
            raise TransientError("timeout")
        return {"result": result}


class FakeClient:
    def __init__(self, whs):
        self.whs = whs
        self.calls = []

    def call(self, wh, step, t, extra):
        self.calls.append((wh, step))
        if extra and extra.get("delay_seconds"):
            self.whs[wh].lost_responses += 1
        return self.whs[wh].apply(t.id, step, t.quantity)


def setup(simulate=None, quantity=30):
    whs = {"WH-001": FakeWarehouse(100), "WH-002": FakeWarehouse(20)}
    client = FakeClient(whs)
    history = []
    saga = Saga(client, lambda t, d: history.append((t.status, d)), sleep=lambda s: None)
    return saga, T(simulate, quantity), whs, history


def test_transferencia_normal():
    saga, t, whs, history = setup()
    saga.run(t)
    assert t.status == COMPLETED
    assert whs["WH-001"].quantity == 70
    assert whs["WH-002"].quantity == 50
    estados = [s for s, _ in history]
    assert estados == [
        "RESERVING_SOURCE",
        "SOURCE_RESERVED",
        "IN_TRANSIT",
        "DESTINATION_RECEIVED",
        "COMPLETED",
    ]


def test_experimento_1_fallo_antes_de_reservar():
    saga, t, whs, _ = setup("fail_before_reserve")
    saga.run(t)
    assert t.status == FAILED
    assert whs["WH-001"].quantity == 100
    assert whs["WH-001"].reserved == 0


def test_experimento_2_fallo_despues_de_reservar():
    saga, t, whs, history = setup("fail_after_reserve")
    saga.run(t)
    assert t.status == RESERVATION_RELEASED
    assert COMPENSATING in [s for s, _ in history]
    assert whs["WH-001"].quantity == 100
    assert whs["WH-001"].reserved == 0
    assert whs["WH-002"].quantity == 20


def test_experimento_3a_destino_caido_desde_el_inicio():
    saga, t, whs, _ = setup()
    whs["WH-002"].down = True
    saga.run(t)
    assert t.status == FAILED
    assert whs["WH-001"].quantity == 100
    assert whs["WH-001"].reserved == 0


def test_experimento_3b_destino_cae_despues_de_despachar():
    saga, t, whs, _ = setup()
    # el destino se cae justo cuando se va a recibir
    original = saga._in_transit

    def caer_y_seguir(tr):
        whs["WH-002"].down = True
        original(tr)

    saga._in_transit = caer_y_seguir
    saga.run(t)
    assert t.status == DESTINATION_PENDING
    assert whs["WH-001"].quantity == 70  # ya salio de origen
    assert whs["WH-002"].quantity == 20

    # sigue caido: el worker reintenta y se queda esperando
    saga.run(t)
    assert t.status == DESTINATION_PENDING

    # el destino vuelve
    whs["WH-002"].down = False
    saga.run(t)
    assert t.status == COMPLETED
    assert whs["WH-002"].quantity == 50


def test_experimento_4_mensaje_duplicado():
    saga, t, whs, _ = setup()
    saga.run(t)
    saga.run(t)  # llega TR-001 otra vez
    assert t.status == COMPLETED
    assert whs["WH-001"].quantity == 70
    assert whs["WH-002"].quantity == 50


def test_experimento_4_duplicado_en_medio_de_la_saga():
    saga, t, whs, _ = setup()
    saga.run(t)
    # otro worker con una copia vieja del mensaje repite todos los pasos
    t2 = T()
    saga.run(t2)
    assert whs["WH-001"].quantity == 70
    assert whs["WH-002"].quantity == 50


def test_experimento_5_timeout_se_reintenta_sin_duplicar():
    saga, t, whs, history = setup("timeout")
    saga.run(t)
    assert t.status == COMPLETED
    assert whs["WH-001"].quantity == 70
    assert whs["WH-001"].reserved == 0
    assert any("timeout" in d for _, d in history)
    assert any("ya estaba hecha" in d for _, d in history)


def test_origen_se_cae_despues_de_reservar():
    saga, t, whs, _ = setup()
    original = whs["WH-001"].apply

    def reservar_y_caer(tid, step, q):
        r = original(tid, step, q)
        if step == "reserve":
            whs["WH-001"].down = True
            raise TransientError("se cayo antes de responder")
        return r

    whs["WH-001"].apply = reservar_y_caer
    saga.run(t)
    # no se sabe si reservo y el origen no responde: queda compensando
    assert t.status == COMPENSATING
    assert whs["WH-001"].reserved == 30

    # el origen vuelve: la compensacion libera la reserva
    whs["WH-001"].down = False
    saga.run(t)
    assert t.status == RESERVATION_RELEASED
    assert whs["WH-001"].reserved == 0
    assert whs["WH-001"].quantity == 100


def test_experimento_6_worker_reiniciado():
    saga, t, whs, _ = setup()
    # el worker se muere justo despues de reservar
    saga2 = Saga(saga.client, saga.save, sleep=lambda s: None)
    original = saga._source_reserved

    def morir(tr):
        raise KeyboardInterrupt

    saga._source_reserved = morir
    try:
        saga.run(t)
    except KeyboardInterrupt:
        pass
    assert t.status == "SOURCE_RESERVED"

    # el worker nuevo retoma desde el estado guardado
    saga2.run(t)
    assert t.status == COMPLETED
    assert whs["WH-001"].quantity == 70
    assert whs["WH-002"].quantity == 50
    assert original  # solo para que ruff no se queje


def test_sin_stock_falla_sin_compensar():
    saga, t, whs, _ = setup(quantity=500)
    saga.run(t)
    assert t.status == FAILED
    assert whs["WH-001"].reserved == 0


def test_despacho_aplicado_pero_sin_respuesta_sigue_adelante():
    saga, t, whs, _ = setup()
    original = whs["WH-001"].apply

    def apply(tid, step, q):
        if step == "dispatch":
            whs["WH-001"].lost_responses = 1
        return original(tid, step, q)

    whs["WH-001"].apply = apply
    saga.retries = 1
    saga.run(t)
    # el despacho si quedo, cancel lo detecta y la saga sigue hacia adelante
    assert t.status == COMPLETED
    assert whs["WH-001"].quantity == 70
    assert whs["WH-002"].quantity == 50
