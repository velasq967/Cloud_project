from typing import List, Optional

from sqlalchemy.orm import Session

from app.modules.products.models import ProductEntity
from app.modules.products.schemas import ProductCreate, ProductUpdate


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, product_in: ProductCreate) -> ProductEntity:
        product = ProductEntity(**product_in.model_dump())
        self.db.add(product)
        self.db.flush()
        return product

    def get_by_id(self, product_id: int) -> Optional[ProductEntity]:
        return self.db.query(ProductEntity).filter(ProductEntity.id == product_id).first()

    def get_by_sku(self, sku: str) -> Optional[ProductEntity]:
        return self.db.query(ProductEntity).filter(ProductEntity.sku == sku).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ProductEntity]:
        return (
            self.db.query(ProductEntity)
            .order_by(ProductEntity.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, product: ProductEntity, changes: ProductUpdate) -> ProductEntity:
        for field, value in changes.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        self.db.add(product)
        return product

    def delete(self, product: ProductEntity) -> None:
        self.db.delete(product)
