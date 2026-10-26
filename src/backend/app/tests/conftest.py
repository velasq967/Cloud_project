import os
import sys
from pathlib import Path

# pytest agrega tests/ al sys.path; agregamos la raíz del backend (/app).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Debe definirse antes de importar app.config / app.main.
os.environ["DATABASE_URL"] = "sqlite:///./test_warehouse.db"
os.environ["WAREHOUSE_ID"] = "WH-TEST"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def product(client):
    response = client.post(
        "/products",
        json={
            "sku": "TEST-001",
            "name": "Producto de prueba",
            "description": "Solo para tests",
            "category": "Test",
            "unit": "unit",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
