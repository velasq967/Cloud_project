import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from central.config import settings

logger = logging.getLogger("central.db")

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def init_db(attempts: int = 30) -> None:
    from central import models  # noqa: F401  registra las tablas

    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            logger.warning("db_not_ready attempt=%s error=%s", attempt, exc)
            time.sleep(2)
    raise RuntimeError("La base central no respondio")
