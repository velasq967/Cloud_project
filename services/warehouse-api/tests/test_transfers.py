def step(client, transfer_id, name, quantity=30, sku="TEST-001"):
    return client.post(
        f"/internal/transfers/{transfer_id}/{name}",
        json={"sku": sku, "quantity": quantity},
    )


def stock(client, product):
    return client.get(f"/inventory/{product['id']}").json()


def recibir(client, product, quantity):
    r = client.post(
        "/inventory/movements",
        json={"product_id": product["id"], "type": "RECEIPT", "quantity": quantity},
    )
    assert r.status_code == 201


def test_reserva_y_despacho(client, product):
    recibir(client, product, 100)

    r = step(client, "TR-1", "reserve")
    assert r.status_code == 200
    assert r.json()["result"] == "reserved"
    assert stock(client, product)["reserved_quantity"] == 30

    r = step(client, "TR-1", "dispatch")
    assert r.json()["result"] == "dispatched"
    s = stock(client, product)
    assert s["quantity"] == 70
    assert s["reserved_quantity"] == 0


def test_reserva_duplicada_no_reserva_dos_veces(client, product):
    recibir(client, product, 100)

    step(client, "TR-2", "reserve")
    r = step(client, "TR-2", "reserve")

    assert r.status_code == 200
    assert r.json()["already_done"] is True
    assert stock(client, product)["reserved_quantity"] == 30


def test_recepcion_duplicada_no_suma_dos_veces(client, product):
    step(client, "TR-3", "receive")
    r = step(client, "TR-3", "receive")

    assert r.json()["already_done"] is True
    assert stock(client, product)["quantity"] == 30


def test_reserva_sin_stock_da_409(client, product):
    recibir(client, product, 10)
    r = step(client, "TR-4", "reserve")
    assert r.status_code == 409
    assert stock(client, product)["reserved_quantity"] == 0


def test_cancel_libera_la_reserva(client, product):
    recibir(client, product, 100)
    step(client, "TR-5", "reserve")

    r = step(client, "TR-5", "cancel")
    assert r.json()["result"] == "released"
    assert stock(client, product)["reserved_quantity"] == 0

    # si el mismo mensaje de reserva llega otra vez no se vuelve a reservar
    r = step(client, "TR-5", "reserve")
    assert r.json()["already_done"] is True
    assert stock(client, product)["reserved_quantity"] == 0


def test_cancel_sin_reserva_no_hace_nada(client, product):
    recibir(client, product, 100)
    r = step(client, "TR-6", "cancel")
    assert r.json()["result"] == "nothing_reserved"
    assert stock(client, product)["reserved_quantity"] == 0


def test_reserva_que_llega_tarde_despues_de_cancelar_se_rechaza(client, product):
    recibir(client, product, 100)
    step(client, "TR-11", "cancel")

    r = step(client, "TR-11", "reserve")
    assert r.status_code == 409
    assert stock(client, product)["reserved_quantity"] == 0


def test_cancel_despues_de_despachar_avisa(client, product):
    recibir(client, product, 100)
    step(client, "TR-7", "reserve")
    step(client, "TR-7", "dispatch")

    r = step(client, "TR-7", "cancel")
    assert r.json()["result"] == "already_dispatched"
    assert stock(client, product)["quantity"] == 70


def test_despacho_sin_reserva_da_409(client, product):
    recibir(client, product, 100)
    r = step(client, "TR-8", "dispatch")
    assert r.status_code == 409


def test_check_producto_inexistente_da_404(client):
    r = step(client, "TR-9", "check", sku="NO-EXISTE")
    assert r.status_code == 404


def test_movimientos_quedan_con_la_referencia(client, product):
    recibir(client, product, 100)
    step(client, "TR-10", "reserve")
    step(client, "TR-10", "dispatch")

    movs = client.get(f"/inventory/{product['id']}/movements").json()
    tipos = [m["type"] for m in movs if m["reference"] == "TR-10"]
    assert sorted(tipos) == ["RESERVATION", "TRANSFER_OUT"]
