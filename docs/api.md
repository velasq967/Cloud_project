# API — Fase 1

Base local: `http://localhost:8001`
Swagger: `http://localhost:8001/docs`

Todas las respuestas incluyen `X-Correlation-ID`. Si el cliente envía ese header, se conserva; si no, se genera.

## Health

### `GET /health`

```json
{
  "status": "ok",
  "database": "ok",
  "warehouse_id": "WH-001"
}
```

Si la base no responde: `503` con `{"status":"degraded","database":"down",...}`.

## Productos

### `POST /products`

```json
{
  "sku": "PROD-001",
  "name": "Caja de herramientas",
  "description": "Caja metálica",
  "category": "Ferretería",
  "unit": "unit"
}
```

- `201`: producto creado. También se crea su fila de inventario en cero.
- `409`: SKU duplicado.
- `422`: datos inválidos.

### `GET /products?skip=0&limit=100`

Lista productos.

### `GET /products/{id}`

- `200`: producto.
- `404`: no existe.

### `PUT /products/{id}`

Actualización parcial. No permite cambiar `sku` en esta fase.

```json
{
  "name": "Nuevo nombre",
  "category": "Nueva categoría"
}
```

### `DELETE /products/{id}`

- `204`: eliminado. Borra en cascada inventario y movimientos.
- `404`: no existe.

## Inventario

### `GET /inventory/{product_id}`

```json
{
  "product_id": 1,
  "warehouse_id": "WH-001",
  "quantity": 100,
  "reserved_quantity": 10,
  "available_quantity": 90,
  "updated_at": "2026-10-26T18:00:00Z"
}
```

`available_quantity = quantity - reserved_quantity`.

### `POST /inventory/movements`

```json
{
  "product_id": 1,
  "type": "RECEIPT",
  "quantity": 10,
  "reference": "FACTURA-001"
}
```

`quantity` siempre es positivo; el `type` define el efecto.

| Tipo | Efecto |
|---|---|
| `RECEIPT` | `quantity += n` |
| `RETURN` | `quantity += n` |
| `TRANSFER_IN` | `quantity += n` |
| `ADJUSTMENT` | `quantity += n` (ajuste positivo) |
| `SHIPMENT` | `quantity -= n` si hay disponible suficiente |
| `TRANSFER_OUT` | `quantity -= n` si hay disponible suficiente |
| `RESERVATION` | `reserved_quantity += n` si hay disponible suficiente |
| `RELEASE` | `reserved_quantity -= n` |

Respuestas:

- `201`: movimiento creado.
- `400`: stock insuficiente, liberación inválida o tipo inválido.
- `404`: producto o inventario no existe.
- `422`: payload inválido.

### `GET /inventory/{product_id}/movements?skip=0&limit=100`

Historial ordenado del más reciente al más antiguo.

```json
[
  {
    "id": 2,
    "product_id": 1,
    "warehouse_id": "WH-001",
    "type": "SHIPMENT",
    "quantity": 4,
    "reference": "ORD-001",
    "correlation_id": "COR-...",
    "created_at": "2026-10-26T18:00:00Z"
  }
]
```

## Errores

Formato estándar de FastAPI:

```json
{
  "detail": "Stock disponible insuficiente. Disponible: 6, solicitado: 15."
}
```
