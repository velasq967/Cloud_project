-- ============================================================
-- Warehouse Cloud Platform — Esquema Fase 1
-- Se ejecuta automáticamente la primera vez que se crea el
-- volumen de PostgreSQL en Docker.
--
-- Para RDS: ejecutar manualmente desde EC2 con psql.
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
