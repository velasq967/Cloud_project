-- ============================================================
-- Datos de ejemplo para desarrollo
-- Idempotente: se puede ejecutar varias veces.
-- ============================================================

INSERT INTO products (sku, name, description, category, unit)
VALUES
    ('PROD-001', 'Caja de herramientas', 'Caja metálica con herramientas básicas', 'Ferretería', 'unit'),
    ('PROD-002', 'Guantes de seguridad', 'Par de guantes de nitrilo', 'Seguridad', 'pair'),
    ('PROD-003', 'Cinta adhesiva', 'Rollo de cinta de embalaje 50 m', 'Empaque', 'roll')
ON CONFLICT (sku) DO NOTHING;

INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity)
SELECT id, 'WH-001', 100, 0 FROM products WHERE sku = 'PROD-001'
ON CONFLICT (product_id, warehouse_id) DO NOTHING;

INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity)
SELECT id, 'WH-001', 250, 10 FROM products WHERE sku = 'PROD-002'
ON CONFLICT (product_id, warehouse_id) DO NOTHING;

INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity)
SELECT id, 'WH-001', 40, 0 FROM products WHERE sku = 'PROD-003'
ON CONFLICT (product_id, warehouse_id) DO NOTHING;
