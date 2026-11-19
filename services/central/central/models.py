from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from central.database import Base


class Transfer(Base):
    __tablename__ = "transfers"

    id = Column(String(50), primary_key=True)
    source_warehouse = Column(String(20), nullable=False)
    destination_warehouse = Column(String(20), nullable=False)
    sku = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, index=True)
    simulate = Column(String(30))
    last_error = Column(Text)
    paused = Column(Boolean, nullable=False, default=False)
    pending_since = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TransferHistory(Base):
    # cada cambio de estado o reintento queda aqui, sirve para ver la saga paso a paso
    __tablename__ = "transfer_history"

    id = Column(Integer, primary_key=True)
    transfer_id = Column(String(50), nullable=False, index=True)
    status = Column(String(30), nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
