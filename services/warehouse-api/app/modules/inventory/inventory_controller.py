from typing import List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.modules.inventory.inventory_service import InventoryService
from app.modules.inventory.models import InventoryEntity
from app.modules.inventory.schemas import (
    InventoryResponse,
    MovementCreate,
    MovementResponse,
)
from app.modules.products.models import ProductEntity

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/{product_id}", response_model=InventoryResponse)
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    return InventoryService(db).get_stock(product_id)


@router.post(
    "/movements",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_movement(payload: MovementCreate, db: Session = Depends(get_db)):
    return InventoryService(db).process_movement(payload)


@router.get("/{product_id}/movements", response_model=List[MovementResponse])
def get_movements(
    product_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_movements(product_id, skip, limit)


# usado por la central (fase 7): reconstruir el read model y la consulta en vivo
internal_router = APIRouter(prefix="/internal", tags=["Inventory (internal)"])


@internal_router.get("/inventory")
def internal_inventory(sku: Optional[str] = None, db: Session = Depends(get_db)):
    query = (
        db.query(ProductEntity, InventoryEntity)
        .join(InventoryEntity, InventoryEntity.product_id == ProductEntity.id)
        .filter(InventoryEntity.warehouse_id == settings.WAREHOUSE_ID)
    )
    if sku:
        query = query.filter(ProductEntity.sku == sku)
    return [
        {
            "sku": product.sku,
            "product_id": product.id,
            "warehouse_id": inventory.warehouse_id,
            "quantity": inventory.quantity,
            "reserved_quantity": inventory.reserved_quantity,
            "available_quantity": inventory.quantity - inventory.reserved_quantity,
            "updated_at": inventory.updated_at,
        }
        for product, inventory in query.order_by(ProductEntity.sku).all()
    ]
