def movement(client, product_id, movement_type, quantity, reference="TEST"):
    return client.post(
        "/inventory/movements",
        json={
            "product_id": product_id,
            "type": movement_type,
            "quantity": quantity,
            "reference": reference,
        },
    )


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["warehouse_id"] == "WH-TEST"
    assert response.headers["X-Correlation-ID"]


def test_correlation_id_is_propagated(client):
    response = client.get("/health", headers={"X-Correlation-ID": "COR-TEST-123"})
    assert response.headers["X-Correlation-ID"] == "COR-TEST-123"


def test_create_product_initializes_inventory(client):
    response = client.post(
        "/products",
        json={
            "sku": "SKU-100",
            "name": "Caja",
            "unit": "unit",
        },
    )
    assert response.status_code == 201
    product = response.json()

    stock = client.get(f"/inventory/{product['id']}")
    assert stock.status_code == 200
    body = stock.json()
    assert body["product_id"] == product["id"]
    assert body["warehouse_id"] == "WH-TEST"
    assert body["quantity"] == 0
    assert body["reserved_quantity"] == 0
    assert body["available_quantity"] == 0
    assert body["updated_at"]


def test_duplicate_sku_returns_409(client, product):
    response = client.post(
        "/products",
        json={
            "sku": product["sku"],
            "name": "Duplicado",
            "unit": "unit",
        },
    )
    assert response.status_code == 409


def test_receipt_increases_stock(client, product):
    response = movement(client, product["id"], "RECEIPT", 10)
    assert response.status_code == 201, response.text

    stock = client.get(f"/inventory/{product['id']}").json()
    assert stock["quantity"] == 10
    assert stock["reserved_quantity"] == 0
    assert stock["available_quantity"] == 10


def test_shipment_rejects_insufficient_stock(client, product):
    movement(client, product["id"], "RECEIPT", 10)

    response = movement(client, product["id"], "SHIPMENT", 11)
    assert response.status_code == 400
    assert "insuficiente" in response.json()["detail"].lower()

    stock = client.get(f"/inventory/{product['id']}").json()
    assert stock["quantity"] == 10


def test_shipment_decreases_stock(client, product):
    movement(client, product["id"], "RECEIPT", 10)
    response = movement(client, product["id"], "SHIPMENT", 4)
    assert response.status_code == 201

    stock = client.get(f"/inventory/{product['id']}").json()
    assert stock["quantity"] == 6
    assert stock["available_quantity"] == 6


def test_reservation_and_release(client, product):
    movement(client, product["id"], "RECEIPT", 10)

    response = movement(client, product["id"], "RESERVATION", 3)
    assert response.status_code == 201

    stock = client.get(f"/inventory/{product['id']}").json()
    assert stock["quantity"] == 10
    assert stock["reserved_quantity"] == 3
    assert stock["available_quantity"] == 7

    response = movement(client, product["id"], "RELEASE", 2)
    assert response.status_code == 201

    stock = client.get(f"/inventory/{product['id']}").json()
    assert stock["quantity"] == 10
    assert stock["reserved_quantity"] == 1
    assert stock["available_quantity"] == 9


def test_reservation_cannot_exceed_available(client, product):
    movement(client, product["id"], "RECEIPT", 2)
    response = movement(client, product["id"], "RESERVATION", 3)
    assert response.status_code == 400
    assert "insuficiente" in response.json()["detail"].lower()


def test_release_cannot_exceed_reserved(client, product):
    response = movement(client, product["id"], "RELEASE", 1)
    assert response.status_code == 400


def test_movements_are_listed_newest_first(client, product):
    movement(client, product["id"], "RECEIPT", 5)
    movement(client, product["id"], "SHIPMENT", 2)

    response = client.get(f"/inventory/{product['id']}/movements")
    assert response.status_code == 200
    movements = response.json()
    assert len(movements) == 2
    assert movements[0]["type"] == "SHIPMENT"
    assert movements[1]["type"] == "RECEIPT"
    assert all(m["correlation_id"] for m in movements)


def test_update_product(client, product):
    response = client.put(
        f"/products/{product['id']}",
        json={"name": "Nombre actualizado", "category": "Nueva"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Nombre actualizado"
    assert response.json()["category"] == "Nueva"


def test_delete_product(client, product):
    response = client.delete(f"/products/{product['id']}")
    assert response.status_code == 204
    assert client.get(f"/products/{product['id']}").status_code == 404
    assert client.get(f"/inventory/{product['id']}").status_code == 404


def test_invalid_movement_type_is_rejected(client, product):
    response = movement(client, product["id"], "INVALID", 1)
    assert response.status_code == 422
