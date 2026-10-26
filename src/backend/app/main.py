from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.correlation import CorrelationIdMiddleware
from app.database import Base, engine
from app.logging_config import configure_logging
from app.modules.health.health_controller import router as health_router
from app.modules.inventory.inventory_controller import router as inventory_router
from app.modules.products.products_controller import router as products_router

configure_logging()
logger = logging.getLogger("warehouse.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En Docker, PostgreSQL ya creó las tablas con db/init.sql.
    # create_all es una red de seguridad para desarrollo local.
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("database_ready")
    except Exception:
        logger.exception("database_init_failed")
    yield


app = FastAPI(
    title=f"{settings.APP_NAME} — {settings.WAREHOUSE_ID}",
    description="Fase 1: una bodega, API + PostgreSQL, inventario transaccional.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(health_router)
app.include_router(products_router)
app.include_router(inventory_router)
