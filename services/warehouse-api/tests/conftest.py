import os
import sys
from pathlib import Path

# pytest agrega tests/ al sys.path; agregamos el servicio y el paquete común.
# En Docker el paquete común ya está instalado y la ruta del monorepo no existe.
TEST_FILE = Path(__file__).resolve()
SERVICE_ROOT = TEST_FILE.parents[1]
candidates = [SERVICE_ROOT]
if len(TEST_FILE.parents) > 3:
    candidates.append(TEST_FILE.parents[3] / "libs" / "common")

for candidate in candidates:
    if candidate.exists():
        sys.path.insert(0, str(candidate))

# Debe definirse antes de importar app.config / app.main.
os.environ["DATABASE_URL"] = "sqlite:///./test_warehouse.db"
os.environ["WAREHOUSE_ID"] = "WH-TEST"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["SEED_ON_START"] = "false"

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
