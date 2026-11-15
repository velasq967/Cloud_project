from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.inventory.inventory_service import InventoryService
from app.modules.products.products_repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.product_repo = ProductRepository(db)
        self.inventory_service = InventoryService(db)

    def create_product_with_inventory(self, product_in: ProductCreate):
        if self.product_repo.get_by_sku(product_in.sku):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El SKU '{product_in.sku}' ya existe.",
            )

        try:
            product = self.product_repo.create(product_in)
            self.inventory_service.initialize_stock(product.id)
            self.db.commit()
            self.db.refresh(product)
            return product
        except HTTPException:
            self.db.rollback()
            raise
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El SKU '{product_in.sku}' ya existe.",
            )
        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creando el producto: {exc}",
            )

    def get_product(self, product_id: int):
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado.",
            )
        return product

    def list_products(self, skip: int, limit: int):
        return self.product_repo.get_all(skip, limit)

    def update_product(self, product_id: int, changes: ProductUpdate):
        product = self.get_product(product_id)
        try:
            self.product_repo.update(product, changes)
            self.db.commit()
            self.db.refresh(product)
            return product
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se pudo actualizar: hay un conflicto de unicidad.",
            )
        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error actualizando el producto: {exc}",
            )

    def delete_product(self, product_id: int) -> None:
        product = self.get_product(product_id)
        try:
            self.product_repo.delete(product)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error eliminando el producto: {exc}",
            )
