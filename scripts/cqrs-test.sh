#!/usr/bin/env bash
# Fase 7: compara la consulta global por read model (B) contra la consulta en vivo (A)
# Uso: make up-multi && bash scripts/cqrs-test.sh

set -uo pipefail

COMPOSE="docker compose --env-file .env -f infrastructure/compose/compose.multi.yml"
CENTRAL="http://localhost:8010"
WH3="http://localhost:8003"
SKU="PROD-001"
OK=0
FALLOS=""

step() { printf "\n==================== %s ====================\n" "$1"; }

num() {  # num campo  (lee json de stdin, primer numero)
  grep -o "\"$1\":[0-9.]*" | head -1 | cut -d: -f2
}

field() {
  grep -o "\"$1\":\"[^\"]*\"" | head -1 | cut -d'"' -f4
}

bool() {
  grep -o "\"$1\":[a-z]*" | head -1 | cut -d: -f2
}

per_wh() {  # muestra cantidad por bodega
  grep -o '"warehouse_id":"WH-[0-9]*","quantity":[0-9]*' | sed 's/"warehouse_id":"\(WH-[0-9]*\)","quantity":\([0-9]*\)/\1=\2/' | tr '\n' ' '
}

result() {
  if [ "$2" = "0" ]; then echo "  >> OK: $1"; OK=$((OK+1)); else echo "  >> FALLO: $1"; FALLOS="$FALLOS\n  - $1"; fi
}

avg_ms() {  # avg_ms url veces -> promedio en ms medido por curl
  local i total=0 t
  for i in $(seq 1 "$2"); do
    t=$(curl -s -o /dev/null -w '%{time_total}' --max-time 10 "$1")
    total=$(awk -v a="$total" -v b="$t" 'BEGIN{print a+b}')
  done
  awk -v t="$total" -v n="$2" 'BEGIN{printf "%.1f", t*1000/n}'
}

wait_wh002() {
  local i
  for i in $(seq 1 60); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://localhost:8002/health)" = "200" ] && return 0
    sleep 2
  done
  return 1
}

# ------------------------------------------------------------------

step "Preparando"
if [ "$(curl -s -o /dev/null -w '%{http_code}' "$CENTRAL/health")" != "200" ]; then
  echo "central-api no responde. Corre make up-multi primero." >&2
  exit 1
fi
echo "  reconstruyendo el read model con una foto de cada bodega:"
echo "  $(curl -s -X POST "$CENTRAL/global/rebuild")"

B=$(curl -s "$CENTRAL/global/inventory/$SKU")
A=$(curl -s "$CENTRAL/global/inventory-live/$SKU")
echo "  B (read model): total=$(echo "$B" | num total_quantity)  $(echo "$B" | per_wh)"
echo "  A (en vivo):    total=$(echo "$A" | num total_quantity)  $(echo "$A" | per_wh)"
[ "$(echo "$B" | num total_quantity)" = "$(echo "$A" | num total_quantity)" ]
result "read model y consulta en vivo dan el mismo total" $?

step "1. Latencia"
echo "  promedio de 30 requests a cada alternativa (todas las bodegas arriba):"
la=$(avg_ms "$CENTRAL/global/inventory-live/$SKU" 30)
lb=$(avg_ms "$CENTRAL/global/inventory/$SKU" 30)
echo "  A (en vivo, llama 3 bodegas): ${la} ms"
echo "  B (read model):               ${lb} ms"
echo "  (para una prueba con carga: make load-cqrs)"

step "2. Consistencia eventual"
P3=$(curl -s "$WH3/products?limit=500" | grep -o "{[^}]*\"sku\":\"$SKU\"[^}]*}" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
antes=$(curl -s "$CENTRAL/global/inventory/$SKU" | num total_quantity)
echo "  total en el read model antes: $antes"
echo "  registrando RECEIPT de 10 unidades en WH-003..."
curl -s -o /dev/null -X POST "$WH3/inventory/movements" -H 'Content-Type: application/json' \
  -d "{\"product_id\":$P3,\"type\":\"RECEIPT\",\"quantity\":10,\"reference\":\"cqrs-test\"}"
inmediato=$(curl -s "$CENTRAL/global/inventory/$SKU" | num total_quantity)
echo "  total en el read model justo despues: $inmediato"
intentos=0
actual=$inmediato
while [ "$actual" != "$((antes + 10))" ] && [ $intentos -lt 50 ]; do
  sleep 0.2
  intentos=$((intentos+1))
  actual=$(curl -s "$CENTRAL/global/inventory/$SKU" | num total_quantity)
done
lag=$(curl -s "$CENTRAL/global/inventory/$SKU" | grep -o '"warehouse_id":"WH-003"[^}]*' | grep -o '"projection_lag_ms":[0-9]*' | cut -d: -f2)
echo "  total en el read model despues de esperar: $actual"
echo "  tiempo entre el evento y la proyeccion (WH-003): ${lag:-?} ms"
[ "$actual" = "$((antes + 10))" ]
result "el read model se pone al dia solo (consistencia eventual)" $?

step "3. Disponibilidad con WH-002 caida"
$COMPOSE stop wh002-api-1 wh002-api-2 wh002-api-3 >/dev/null 2>&1
echo "  WH-002 apagada"
sleep 2
code_b=$(curl -s -o /tmp/cqrs_b.json -w '%{http_code}' "$CENTRAL/global/inventory/$SKU")
tb=$(curl -s -o /dev/null -w '%{time_total}' "$CENTRAL/global/inventory/$SKU")
code_a=$(curl -s -o /tmp/cqrs_a.json -w '%{http_code}' "$CENTRAL/global/inventory-live/$SKU")
ta=$(curl -s -o /dev/null -w '%{time_total}' "$CENTRAL/global/inventory-live/$SKU")
echo "  B (read model): HTTP $code_b en $(awk -v t="$tb" 'BEGIN{printf "%.0f", t*1000}') ms -> total=$(num total_quantity < /tmp/cqrs_b.json)  $(per_wh < /tmp/cqrs_b.json)"
echo "  A (en vivo):    HTTP $code_a en $(awk -v t="$ta" 'BEGIN{printf "%.0f", t*1000}') ms -> total=$(num total_quantity < /tmp/cqrs_a.json)  $(per_wh < /tmp/cqrs_a.json) complete=$(bool complete < /tmp/cqrs_a.json)"
echo "  errores de A: $(grep -o '"errors":\[[^]]*\]' /tmp/cqrs_a.json)"
[ "$code_b" = "200" ] && grep -q '"WH-002"' /tmp/cqrs_b.json
result "B sigue respondiendo con las 3 bodegas (ultimo dato conocido de WH-002)" $?
[ "$(bool complete < /tmp/cqrs_a.json)" = "false" ]
result "A responde incompleto sin WH-002" $?
echo "  prendiendo WH-002..."
$COMPOSE start wh002-api-1 wh002-api-2 wh002-api-3 >/dev/null 2>&1
wait_wh002
rm -f /tmp/cqrs_a.json /tmp/cqrs_b.json

step "Resumen"
echo "  pruebas OK: $OK de 4"
if [ -n "$FALLOS" ]; then printf "  fallaron:%b\n" "$FALLOS"; exit 1; fi
echo "  OK: comparacion A vs B terminada"
