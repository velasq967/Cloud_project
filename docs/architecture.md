# Arquitectura — Fase 1

## Diagrama

```text
+-------------------+
|     Navegador     |
+---------+---------+
          |
          | HTTP :8081
          v
+-------------------+        /api/*        +-------------------+
|  Nginx frontend   | -------------------> |  FastAPI (WH-001) |
|  HTML/CSS/JS      |                      |  Uvicorn :8000    |
+-------------------+                      +---------+---------+
                                                     |
                                                     | SQLAlchemy
                                                     v
                                           +-------------------+
                                           |   PostgreSQL 16   |
                                           |   warehouse_db    |
                                           +-------------------+
```

En AWS:

```text
Internet
   |
   v
EC2 (Docker Compose)
   |-- frontend (Nginx :80)
   |-- api (FastAPI :8000)
   |
   v
RDS PostgreSQL (privado)
```

## Componentes

### Frontend

- HTML, CSS y JavaScript sin build.
- Nginx sirve archivos estáticos y hace proxy de `/api` hacia la API.
- Evita CORS y expone un solo origen al usuario.
- `API_TARGET` se inyecta por variable de entorno al iniciar el contenedor.

### API

- FastAPI + Uvicorn.
- Arquitectura modular por dominio: `health`, `products`, `inventory`.
- Capas: controller → service → repository → model.
- La transacción se controla en el service.
- `SELECT ... FOR UPDATE` bloquea la fila de inventario antes de modificarla.

### Base de datos

- PostgreSQL 16.
- Tablas: `products`, `inventory`, `inventory_movements`.
- Restricciones:
  - `inventory (product_id, warehouse_id)` único.
  - `quantity >= 0`.
  - `reserved_quantity >= 0`.
  - `reserved_quantity <= quantity`.
  - `quantity > 0` en movimientos.
  - Tipo de movimiento válido.

## Flujo de un movimiento

```text
POST /inventory/movements
        |
        v
1. Validar producto
2. SELECT inventory ... FOR UPDATE
3. Calcular disponible = quantity - reserved
4. Aplicar regla según tipo
5. UPDATE inventory
6. INSERT inventory_movements
7. COMMIT
        |
        +--> si algo falla: ROLLBACK
```

## Observabilidad

- `X-Correlation-ID`: se recibe o se genera por request.
- Se devuelve en la respuesta.
- Se guarda en `inventory_movements.correlation_id`.
- Logs JSON con `timestamp`, `level`, `service`, `warehouse_id`, `correlation_id`.

## Decisiones de esta fase

Ver [decisions.md](decisions.md).
