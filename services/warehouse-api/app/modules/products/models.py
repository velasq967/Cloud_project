from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ProductEntity(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    unit = Column(String(20), nullable=False, default="unit")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    inventory = relationship(
        "InventoryEntity",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    movements = relationship(
        "InventoryMovementEntity",
        back_populates="product",
        cascade="all, delete-orphan",
    )
