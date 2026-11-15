from warehouse_common.database import Base, build_engine, build_session_factory  # noqa: F401

from app.config import settings

engine = build_engine(settings.DATABASE_URL)
SessionLocal = build_session_factory(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
