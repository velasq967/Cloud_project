"""Carga datos de ejemplo de forma idempotente."""

from app.config import settings
from app.database import SessionLocal
from app.modules.inventory.models import InventoryEntity
from app.modules.products.models import ProductEntity
from sqlalchemy.orm import Session

SEED = [
    {
        "sku": "PROD-001",
        "name": "Caja de herramientas",
        "description": "Caja metálica con herramientas básicas",
        "category": "Ferretería",
        "unit": "unit",
        "quantity": 100,
        "reserved": 0,
    },
    {
        "sku": "PROD-002",
        "name": "Guantes de seguridad",
        "description": "Par de guantes de nitrilo",
        "category": "Seguridad",
        "unit": "pair",
        "quantity": 250,
        "reserved": 10,
    },
    {
        "sku": "PROD-003",
        "name": "Cinta adhesiva",
        "description": "Rollo de cinta de embalaje 50 m",
        "category": "Empaque",
        "unit": "roll",
        "quantity": 40,
        "reserved": 0,
    },
]


def seed(db: Session) -> None:
    for item in SEED:
        product = (
            db.query(ProductEntity).filter(ProductEntity.sku == item["sku"]).first()
        )
        if not product:
            product = ProductEntity(
                sku=item["sku"],
                name=item["name"],
                description=item["description"],
                category=item["category"],
                unit=item["unit"],
            )
            db.add(product)
            db.flush()

        inventory = (
            db.query(InventoryEntity)
            .filter(
                InventoryEntity.product_id == product.id,
                InventoryEntity.warehouse_id == settings.WAREHOUSE_ID,
            )
            .first()
        )
        if not inventory:
            db.add(
                InventoryEntity(
                    product_id=product.id,
                    warehouse_id=settings.WAREHOUSE_ID,
                    quantity=item["quantity"],
                    reserved_quantity=item["reserved"],
                )
            )
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
        print(f"seed_ready warehouse={settings.WAREHOUSE_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
