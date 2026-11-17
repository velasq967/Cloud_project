from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base

MOVEMENT_TYPES = (
    "RECEIPT",
    "SHIPMENT",
    "ADJUSTMENT",
    "RESERVATION",
    "RELEASE",
    "TRANSFER_OUT",
    "TRANSFER_IN",
    "RETURN",
)


class InventoryEntity(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_id = Column(String(50), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product = relationship("ProductEntity", back_populates="inventory")

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "warehouse_id",
            name="uq_inventory_product_warehouse",
        ),
        CheckConstraint("quantity >= 0", name="chk_inventory_quantity_non_negative"),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="chk_inventory_reserved_non_negative",
        ),
        CheckConstraint(
            "reserved_quantity <= quantity",
            name="chk_inventory_reserved_le_quantity",
        ),
    )


class InventoryMovementEntity(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_id = Column(String(50), nullable=False, index=True)
    type = Column(String(30), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String(100))
    correlation_id = Column(String(100))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    product = relationship("ProductEntity", back_populates="movements")

    __table_args__ = (
        CheckConstraint(
            "type IN ('RECEIPT','SHIPMENT','ADJUSTMENT','RESERVATION',"
            "'RELEASE','TRANSFER_OUT','TRANSFER_IN','RETURN')",
            name="chk_movement_type",
        ),
        CheckConstraint("quantity > 0", name="chk_movement_quantity_positive"),
    )
