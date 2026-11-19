import httpx

from central.config import settings
from central.saga import BusinessError, TransientError


class WarehouseClient:
    """Llama los endpoints /internal/transfers de cada bodega."""

    def __init__(self, urls=None, timeout=None):
        self.urls = urls or settings.warehouses
        self.http = httpx.Client(timeout=timeout or settings.REQUEST_TIMEOUT)

    def call(self, warehouse, step, t, extra=None):
        base = self.urls.get(warehouse)
        if not base:
            raise BusinessError(f"bodega desconocida {warehouse}")
        body = {"sku": t.sku, "quantity": t.quantity}
        if extra:
            body.update(extra)
        try:
            r = self.http.post(
                f"{base}/internal/transfers/{t.id}/{step}",
                json=body,
                headers={"X-Correlation-ID": t.id},
            )
        except httpx.TimeoutException:
            raise TransientError("timeout")
        except httpx.TransportError as exc:
            raise TransientError(f"sin conexion ({exc.__class__.__name__})")

        if r.status_code >= 500:
            raise TransientError(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except Exception:
                detail = r.text
            raise BusinessError(f"HTTP {r.status_code}: {detail}")
        return r.json()
