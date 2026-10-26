import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.correlation import get_correlation_id
from app.modules.inventory.inventory_repository import InventoryRepository
from app.modules.inventory.schemas import InventoryResponse, MovementCreate, MovementType
from app.modules.products.products_repository import ProductRepository

logger = logging.getLogger("warehouse.inventory")


class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InventoryRepository(db)
        self.product_repo = ProductRepository(db)

    def initialize_stock(self, product_id: int) -> None:
        self.repo.initialize_inventory(product_id)

    def get_stock(self, product_id: int) -> InventoryResponse:
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado.",
            )

        inventory = self.repo.get_by_product(product_id)
        if not inventory:
            # Un producto recién creado siempre tiene inventario, pero se
            # devuelve un saldo en cero si por alguna razón no existe.
            return InventoryResponse(
                product_id=product_id,
                warehouse_id=settings.WAREHOUSE_ID,
                quantity=0,
                reserved_quantity=0,
                available_quantity=0,
                updated_at=product.updated_at,
            )

        return InventoryResponse(
            product_id=inventory.product_id,
            warehouse_id=inventory.warehouse_id,
            quantity=inventory.quantity,
            reserved_quantity=inventory.reserved_quantity,
            available_quantity=inventory.quantity - inventory.reserved_quantity,
            updated_at=inventory.updated_at,
        )

    def process_movement(self, movement_in: MovementCreate):
        try:
            product = self.product_repo.get_by_id(movement_in.product_id)
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Producto no encontrado.",
                )

            inventory = self.repo.get_by_product_for_update(movement_in.product_id)
            if not inventory:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="El inventario del producto no está inicializado.",
                )

            quantity = movement_in.quantity
            movement_type = movement_in.type
            available = inventory.quantity - inventory.reserved_quantity
            new_quantity = inventory.quantity
            new_reserved = inventory.reserved_quantity

            if movement_type in (
                MovementType.RECEIPT,
                MovementType.TRANSFER_IN,
                MovementType.RETURN,
                MovementType.ADJUSTMENT,
            ):
                new_quantity += quantity

            elif movement_type in (
                MovementType.SHIPMENT,
                MovementType.TRANSFER_OUT,
            ):
                if available < quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Stock disponible insuficiente. "
                            f"Disponible: {available}, solicitado: {quantity}."
                        ),
                    )
                new_quantity -= quantity

            elif movement_type == MovementType.RESERVATION:
                if available < quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Stock disponible insuficiente para reservar. "
                            f"Disponible: {available}, solicitado: {quantity}."
                        ),
                    )
                new_reserved += quantity

            elif movement_type == MovementType.RELEASE:
                if new_reserved < quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "No se puede liberar más de lo reservado. "
                            f"Reservado: {new_reserved}, solicitado: {quantity}."
                        ),
                    )
                new_reserved -= quantity

            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tipo de movimiento inválido.",
                )

            self.repo.update_stock(inventory, new_quantity, new_reserved)
            movement = self.repo.register_movement(
                product_id=movement_in.product_id,
                movement_type=movement_type.value,
                quantity=quantity,
                reference=movement_in.reference,
                correlation_id=get_correlation_id(),
            )

            # Inventario y movimiento se confirman en la misma transacción.
            self.db.commit()
            self.db.refresh(movement)

            logger.info(
                "inventory_movement_processed",
                extra={
                    "extra_fields": {
                        "movement_id": movement.id,
                        "movement_type": movement_type.value,
                        "product_id": movement_in.product_id,
                        "warehouse_id": settings.WAREHOUSE_ID,
                        "quantity": quantity,
                        "resulting_quantity": new_quantity,
                        "resulting_reserved": new_reserved,
                    }
                },
            )
            return movement

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception("inventory_movement_failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error procesando el movimiento: {exc}",
            )

    def get_movements(self, product_id: int, skip: int = 0, limit: int = 100):
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado.",
            )
        return self.repo.get_movements_by_product(product_id, skip, limit)
