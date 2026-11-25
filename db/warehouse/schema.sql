-- ============================================================
-- Warehouse Cloud Platform — Esquema Fase 1 (referencia)
--
-- La fuente de verdad del esquema es Alembic:
--   services/warehouse-api/migrations/
--
-- Este archivo sirve como documentación y como alternativa manual
-- para inicializar una base sin Alembic.
--
-- Si se aplica este archivo en una base existente, ejecutar luego:
--   alembic stamp head
-- ============================================================

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    sku         VARCHAR(50) NOT NULL,
    name        VARCHAR(150) NOT NULL,
    description TEXT,
    category    VARCHAR(100),
    unit        VARCHAR(20) NOT NULL DEFAULT 'unit',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_products_sku ON products (sku);

CREATE TABLE IF NOT EXISTS inventory (
    id                SERIAL PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    warehouse_id      VARCHAR(50) NOT NULL,
    quantity          INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_inventory_product_warehouse UNIQUE (product_id, warehouse_id),
    CONSTRAINT chk_inventory_quantity_non_negative CHECK (quantity >= 0),
    CONSTRAINT chk_inventory_reserved_non_negative CHECK (reserved_quantity >= 0),
    CONSTRAINT chk_inventory_reserved_le_quantity CHECK (reserved_quantity <= quantity)
);

CREATE INDEX IF NOT EXISTS ix_inventory_product_id ON inventory (product_id);
CREATE INDEX IF NOT EXISTS ix_inventory_warehouse_id ON inventory (warehouse_id);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id             SERIAL PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    warehouse_id   VARCHAR(50) NOT NULL,
    type           VARCHAR(30) NOT NULL,
    quantity       INTEGER NOT NULL,
    reference      VARCHAR(100),
    correlation_id VARCHAR(100),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_movement_type CHECK (
        type IN (
            'RECEIPT', 'SHIPMENT', 'ADJUSTMENT', 'RESERVATION',
            'RELEASE', 'TRANSFER_OUT', 'TRANSFER_IN', 'RETURN'
        )
    ),
    CONSTRAINT chk_movement_quantity_positive CHECK (quantity > 0)
);

CREATE INDEX IF NOT EXISTS ix_movements_product_id ON inventory_movements (product_id);
CREATE INDEX IF NOT EXISTS ix_movements_warehouse_id ON inventory_movements (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_movements_created_at ON inventory_movements (created_at);

-- Fase 3: auditoria y reportes
CREATE TABLE IF NOT EXISTS audit_log (
    id             SERIAL PRIMARY KEY,
    event_id       VARCHAR(100) NOT NULL,
    consumer       VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    warehouse_id   VARCHAR(50) NOT NULL,
    correlation_id VARCHAR(100),
    payload        JSON,
    occurred_at    TIMESTAMPTZ,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_audit_event_consumer UNIQUE (event_id, consumer)
);

CREATE TABLE IF NOT EXISTS report_jobs (
    id             VARCHAR(36) PRIMARY KEY,
    type           VARCHAR(50) NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    result         JSON,
    error          TEXT,
    correlation_id VARCHAR(100)
);

-- Fase 6: idempotencia de pasos de transferencia
CREATE TABLE IF NOT EXISTS transfer_operations (
    id          SERIAL PRIMARY KEY,
    transfer_id VARCHAR(50) NOT NULL,
    step        VARCHAR(20) NOT NULL,
    product_id  INTEGER NOT NULL,
    quantity    INTEGER NOT NULL,
    result      VARCHAR(30) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_transfer_operation_step UNIQUE (transfer_id, step)
);

-- Fase 10: outbox e idempotencia de consumidores
CREATE TABLE IF NOT EXISTS outbox_events (
    id             SERIAL PRIMARY KEY,
    event_id       VARCHAR(100) NOT NULL UNIQUE,
    event_type     VARCHAR(100) NOT NULL,
    routing_key    VARCHAR(200) NOT NULL,
    correlation_id VARCHAR(100),
    payload        JSON NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at   TIMESTAMPTZ,
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT
);

CREATE TABLE IF NOT EXISTS processed_events (
    event_id     VARCHAR(100) NOT NULL,
    consumer     VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, consumer)
);
