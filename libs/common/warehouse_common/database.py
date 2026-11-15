from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()


def build_engine(database_url: str, echo: bool = False) -> Engine:
    """Crea un engine con pool_pre_ping para tolerar reinicios de PostgreSQL."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        echo=echo,
        connect_args=connect_args,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )


def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
