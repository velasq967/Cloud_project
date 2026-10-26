# Warehouse Cloud Platform — Fase 1

Plataforma de gestión de una bodega (WH-001) con **FastAPI + PostgreSQL + Nginx + Docker**.

Este repositorio implementa la **Fase 1** del proyecto integrador de Computación en la Nube e Internet de las Cosas:

```text
Navegador
    |
    v
Nginx (frontend estático + proxy /api)
    |
    v
FastAPI (una bodega: WH-001)
    |
    v
PostgreSQL
```

## Alcance actual

- CRUD de productos.
- Inventario por producto y bodega.
- Movimientos: `RECEIPT`, `SHIPMENT`, `ADJUSTMENT`, `RESERVATION`, `RELEASE`, `TRANSFER_IN`, `TRANSFER_OUT`, `RETURN`.
- Regla de negocio: el stock nunca queda negativo.
- Transacción atómica: inventario + movimiento.
- Bloqueo pesimista con `SELECT ... FOR UPDATE`.
- Health check con verificación de base de datos.
- Correlation ID y logs JSON.
- Frontend para alta de productos, movimientos, stock e historial.
- Docker Compose de desarrollo.
- Docker Compose de producción para EC2 + RDS.
- Tests con pytest.
- Seed de datos.

**Fuera de alcance por ahora**: Redis, RabbitMQ, workers, múltiples bodegas, load balancer, Saga, CQRS, S3 batch, Lambda e IoT. Se incorporan en fases posteriores.

## Estructura

```text
.
├── db/
│   ├── init.sql
│   └── seed.sql
├── docs/
├── scripts/
├── src/
│   ├── backend/app/
│   │   ├── app/
│   │   │   ├── modules/
│   │   │   │   ├── health/
│   │   │   │   ├── products/
│   │   │   │   └── inventory/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── correlation.py
│   │   │   └── logging_config.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   └── requirements.txt
│   └── frontend/app/
│       ├── Dockerfile
│       ├── default.conf.template
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
└── README.md
```

## Inicio rápido (Docker)

### 1. Requisitos

- Docker Desktop con WSL2.
- Git.

```powershell
docker --version
docker compose version
```

### 2. Configurar variables

```powershell
Copy-Item .env.example .env
```

### 3. Levantar

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

### 4. Abrir

| Servicio | URL |
|---|---|
| Frontend | http://localhost:8081 |
| API / Swagger | http://localhost:8001/docs |
| Health | http://localhost:8001/health |

### 5. Apagar

```powershell
docker compose down
docker compose down -v   # también borra los datos de PostgreSQL
```

> `db/init.sql` y `db/seed.sql` solo se ejecutan cuando el volumen de PostgreSQL se crea por primera vez. Si cambias el esquema en desarrollo, usa `docker compose down -v` y vuelve a levantar.

## Tests

Dentro del contenedor de la API:

```powershell
docker compose exec api pytest -q
```

Los tests usan SQLite en memoria/archivo para validar reglas de negocio. La integración real con PostgreSQL se valida con el smoke test.

## Smoke test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1
```

o en Linux/macOS:

```bash
bash scripts/smoke-test.sh
```

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de API y base de datos |
| GET | `/products` | Listar productos |
| POST | `/products` | Crear producto e inicializar inventario |
| GET | `/products/{id}` | Obtener producto |
| PUT | `/products/{id}` | Actualizar producto |
| DELETE | `/products/{id}` | Eliminar producto |
| GET | `/inventory/{product_id}` | Stock, reservado y disponible |
| POST | `/inventory/movements` | Registrar movimiento |
| GET | `/inventory/{product_id}/movements` | Historial de movimientos |

Documentación detallada: [docs/api.md](docs/api.md).

## Reglas de inventario

- `quantity` = stock físico total.
- `reserved_quantity` = unidades reservadas.
- `available_quantity = quantity - reserved_quantity`.
- `SHIPMENT` y `TRANSFER_OUT` solo pueden sacar stock **disponible**.
- `RESERVATION` aumenta `reserved_quantity`.
- `RELEASE` disminuye `reserved_quantity`.
- `ADJUSTMENT` en esta fase solo es positivo.
- Todo movimiento se registra en `inventory_movements` dentro de la misma transacción.

Ver [docs/decisions.md](docs/decisions.md) para el detalle y los trade-offs.

## Ramas

`main` es la base estable de integración. Cada integrante trabaja en su rama personal:

| Rama | Integrante |
|---|---|
| `main` | Base estable / integración |
| `phanor` | Phanor |
| `santiago` | Santiago |
| `velasco` | Velasco |

Flujo sugerido:

```powershell
git switch phanor
# trabajar
git add .
git commit -m "phanor: ..."
git push -u origin phanor
```

Luego se integra a `main` con Pull Request.

## AWS

El despliegue objetivo de esta fase es:

```text
Internet -> EC2 (Docker Compose) -> API -> RDS PostgreSQL
```

- Imágenes en Amazon ECR.
- Base de datos en Amazon RDS.
- S3 se deja preparado para la Fase 8.
- Cuenta de AWS Academy Learner Lab: usar la sesión, el rol y las credenciales del laboratorio.

Resumen en [docs/aws-deploy.md](docs/aws-deploy.md). El paso a paso detallado está en la carpeta externa `manuales-proyecto/`.

## Documentación

- [Arquitectura](docs/architecture.md)
- [API](docs/api.md)
- [Decisiones y trade-offs](docs/decisions.md)
- [Despliegue AWS](docs/aws-deploy.md)

## Equipo

Proyecto del curso **Computación en la Nube e Internet de las Cosas**.
