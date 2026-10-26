#!/usr/bin/env bash
# Smoke test Fase 1 — ejecutar con el stack levantado.
set -euo pipefail

API="${API_BASE:-http://localhost:8001}"
SKU="SMOKE-$(date +%Y%m%d%H%M%S)"

step() { printf "\n==> %s\n" "$1"; }

assert_equal() {
  local expected="$1" actual="$2" label="$3"
  if [ "$expected" != "$actual" ]; then
    echo "Fallo en '$label': esperado=$expected actual=$actual" >&2
    exit 1
  fi
  echo "OK  $label = $actual"
}

json_get() {
  python3 -c "import json,sys; print(json.load(sys.stdin)$1)"
}

step "Health"
health="$(curl -fsS "$API/health")"
assert_equal "ok" "$(printf '%s' "$health" | json_get "['status']")" "status"
assert_equal "ok" "$(printf '%s' "$health" | json_get "['database']")" "database"

step "Crear producto $SKU"
product="$(curl -fsS -X POST "$API/products" \
  -H 'Content-Type: application/json' \
  -d "{\"sku\":\"$SKU\",\"name\":\"Producto smoke test\",\"category\":\"Test\",\"unit\":\"unit\"}")"
product_id="$(printf '%s' "$product" | json_get "['id']")"
echo "Producto id=$product_id"

step "Inventario inicial en cero"
stock="$(curl -fsS "$API/inventory/$product_id")"
assert_equal "0" "$(printf '%s' "$stock" | json_get "['quantity']")" "quantity"
assert_equal "0" "$(printf '%s' "$stock" | json_get "['available_quantity']")" "available_quantity"

step "Entrada de 10 unidades"
curl -fsS -X POST "$API/inventory/movements" \
  -H 'Content-Type: application/json' \
  -d "{\"product_id\":$product_id,\"type\":\"RECEIPT\",\"quantity\":10,\"reference\":\"SMOKE-IN\"}" >/dev/null

stock="$(curl -fsS "$API/inventory/$product_id")"
assert_equal "10" "$(printf '%s' "$stock" | json_get "['quantity']")" "quantity"
assert_equal "10" "$(printf '%s' "$stock" | json_get "['available_quantity']")" "available_quantity"

step "Reserva de 3 unidades"
curl -fsS -X POST "$API/inventory/movements" \
  -H 'Content-Type: application/json' \
  -d "{\"product_id\":$product_id,\"type\":\"RESERVATION\",\"quantity\":3,\"reference\":\"SMOKE-RES\"}" >/dev/null

stock="$(curl -fsS "$API/inventory/$product_id")"
assert_equal "3" "$(printf '%s' "$stock" | json_get "['reserved_quantity']")" "reserved_quantity"
assert_equal "7" "$(printf '%s' "$stock" | json_get "['available_quantity']")" "available_quantity"

step "Salida de 4 unidades"
curl -fsS -X POST "$API/inventory/movements" \
  -H 'Content-Type: application/json' \
  -d "{\"product_id\":$product_id,\"type\":\"SHIPMENT\",\"quantity\":4,\"reference\":\"SMOKE-OUT\"}" >/dev/null

stock="$(curl -fsS "$API/inventory/$product_id")"
assert_equal "6" "$(printf '%s' "$stock" | json_get "['quantity']")" "quantity"
assert_equal "3" "$(printf '%s' "$stock" | json_get "['available_quantity']")" "available_quantity"

step "Salida inválida de 99 unidades (debe fallar)"
status="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$API/inventory/movements" \
  -H 'Content-Type: application/json' \
  -d "{\"product_id\":$product_id,\"type\":\"SHIPMENT\",\"quantity\":99,\"reference\":\"SMOKE-FAIL\"}")"
assert_equal "400" "$status" "HTTP status"

step "Historial"
movements="$(curl -fsS "$API/inventory/$product_id/movements")"
count="$(printf '%s' "$movements" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
assert_equal "3" "$count" "movimientos"

step "Eliminar producto de prueba"
curl -fsS -X DELETE "$API/products/$product_id" >/dev/null
echo "OK  producto eliminado"

printf "\nSmoke test completado correctamente.\n"
