from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text, func

from central.database import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(100), unique=True, nullable=False, index=True)
    warehouse_id = Column(String(20), nullable=False, index=True)
    sensor_id = Column(String(50), nullable=False, index=True)
    sensor_type = Column(String(30), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False, default="")
    sequence_number = Column(BigInteger, nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SensorState(Base):
    """Último estado conocido por bodega + sensor, para tolerar desorden."""

    __tablename__ = "sensor_state"

    warehouse_id = Column(String(20), primary_key=True)
    sensor_id = Column(String(50), primary_key=True)
    sensor_type = Column(String(30), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False, default="")
    last_sequence_number = Column(BigInteger, nullable=False)
    last_occurred_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IotAlert(Base):
    __tablename__ = "iot_alerts"

    id = Column(Integer, primary_key=True)
    alert_id = Column(String(150), unique=True, nullable=False, index=True)
    warehouse_id = Column(String(20), nullable=False, index=True)
    sensor_id = Column(String(50), nullable=False, index=True)
    rule = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    value = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class SensorStat(Base):
    __tablename__ = "sensor_stats"

    warehouse_id = Column(String(20), primary_key=True)
    sensor_id = Column(String(50), primary_key=True)
    sensor_type = Column(String(30), nullable=False)
    count = Column(Integer, nullable=False, default=0)
    min_value = Column(Float, nullable=False)
    max_value = Column(Float, nullable=False)
    avg_value = Column(Float, nullable=False)
    last_value = Column(Float, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id = Column(String(100), primary_key=True)
    consumer = Column(String(100), primary_key=True)
    processed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
