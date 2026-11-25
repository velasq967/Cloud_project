from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func

from app.database import Base


class OutboxEventEntity(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    routing_key = Column(String(200), nullable=False)
    correlation_id = Column(String(100), index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
