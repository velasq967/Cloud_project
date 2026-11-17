import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_request_logger = logging.getLogger("warehouse.request")

HEADER_NAME = "X-Correlation-ID"


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str | None = None) -> str:
    correlation_id = value or str(uuid.uuid4())
    _correlation_id.set(correlation_id)
    return correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Propaga X-Correlation-ID y lo deja disponible para los logs."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(HEADER_NAME) or str(uuid.uuid4())
        token = _correlation_id.set(correlation_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            _request_logger.exception(
                "request_failed",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "elapsed_ms": elapsed_ms,
                        "correlation_id": correlation_id,
                    }
                },
            )
            raise
        finally:
            _correlation_id.reset(token)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[HEADER_NAME] = correlation_id
        _request_logger.info(
            "request_completed",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "correlation_id": correlation_id,
                }
            },
        )
        return response
