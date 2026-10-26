from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.modules.inventory.models import InventoryEntity, InventoryMovementEntity


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def initialize_inventory(self, product_id: int) -> InventoryEntity:
        inventory = InventoryEntity(
            product_id=product_id,
            warehouse_id=settings.WAREHOUSE_ID,
            quantity=0,
            reserved_quantity=0,
        )
        self.db.add(inventory)
        return inventory

    def get_by_product_for_update(
        self, product_id: int
    ) -> Optional[InventoryEntity]:
        # Lock pesimista de fila: evita sobreventa bajo concurrencia.
        return (
            self.db.query(InventoryEntity)
            .filter(
                InventoryEntity.product_id == product_id,
                InventoryEntity.warehouse_id == settings.WAREHOUSE_ID,
            )
            .with_for_update()
            .first()
        )

    def get_by_product(self, product_id: int) -> Optional[InventoryEntity]:
        return (
            self.db.query(InventoryEntity)
            .filter(
                InventoryEntity.product_id == product_id,
                InventoryEntity.warehouse_id == settings.WAREHOUSE_ID,
            )
            .first()
        )

    def update_stock(
        self,
        inventory: InventoryEntity,
        quantity: int,
        reserved_quantity: int,
    ) -> None:
        inventory.quantity = quantity
        inventory.reserved_quantity = reserved_quantity
        self.db.add(inventory)

    def register_movement(
        self,
        product_id: int,
        movement_type: str,
        quantity: int,
        reference: Optional[str],
        correlation_id: Optional[str],
    ) -> InventoryMovementEntity:
        movement = InventoryMovementEntity(
            product_id=product_id,
            warehouse_id=settings.WAREHOUSE_ID,
            type=movement_type,
            quantity=quantity,
            reference=reference,
            correlation_id=correlation_id,
        )
        self.db.add(movement)
        return movement

    def get_movements_by_product(
        self,
        product_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[InventoryMovementEntity]:
        return (
            self.db.query(InventoryMovementEntity)
            .filter(
                InventoryMovementEntity.product_id == product_id,
                InventoryMovementEntity.warehouse_id == settings.WAREHOUSE_ID,
            )
            .order_by(
                InventoryMovementEntity.created_at.desc(),
                InventoryMovementEntity.id.desc(),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
