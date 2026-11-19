from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func

from app.database import Base


class TransferOperationEntity(Base):
    # cada paso de una transferencia que ya se aplico en esta bodega.
    # el unique (transfer_id, step) es lo que hace los pasos idempotentes
    __tablename__ = "transfer_operations"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(String(50), nullable=False, index=True)
    step = Column(String(20), nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    result = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("transfer_id", "step", name="uq_transfer_operation_step"),
    )
