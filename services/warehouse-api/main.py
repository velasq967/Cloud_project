import logging
import os
import socket
from contextlib import asynccontextmanager

from app.config import settings
from app.correlation import CorrelationIdMiddleware
from app.logging_config import configure_logging
from app.modules.health.health_controller import router as health_router
from app.modules.inventory.inventory_controller import router as inventory_router
from app.modules.products.products_controller import router as products_router
from app.modules.reports.reports_controller import router as reports_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

configure_logging()
logger = logging.getLogger("warehouse.startup")

# nombre de la replica, sirve para ver el balanceo (fase 5)
INSTANCE_ID = os.getenv("INSTANCE_ID") or socket.gethostname()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema lo administra Alembic (ver scripts/entrypoint.sh).
    # Los tests crean las tablas desde su propia fixture.
    logger.info("application_started")
    yield
    logger.info("application_stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title=f"{settings.APP_NAME} — {settings.WAREHOUSE_ID}",
        description=(
            "Fase 1: una bodega, API + PostgreSQL, inventario transaccional."
        ),
        version="1.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(CorrelationIdMiddleware)

    @application.middleware("http")
    async def instance_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Instance-Id"] = INSTANCE_ID
        return response

    application.include_router(health_router)
    application.include_router(products_router)
    application.include_router(inventory_router)
    application.include_router(reports_router)

    @application.get("/", include_in_schema=False)
    def root():
        return {
            "service": settings.SERVICE_NAME,
            "warehouse_id": settings.WAREHOUSE_ID,
            "instance": INSTANCE_ID,
            "docs": "/docs",
            "health": "/health",
        }

    return application


app = create_app()
