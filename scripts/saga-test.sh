#!/usr/bin/env bash
# Fase 6: transferencia WH-001 -> WH-002 y los 6 experimentos de fallo
# Uso: make up-multi && bash scripts/saga-test.sh
# Compatible con el bash 3.2 de mac (sin jq ni declare -A)

set -uo pipefail

COMPOSE="docker compose --env-file .env -f infrastructure/compose/compose.multi.yml"
CENTRAL="http://localhost:8010"
WH1="http://localhost:8001"
WH2="http://localhost:8002"
SKU="PROD-001"
PASSED=0
FAILED_TESTS=""

step() { printf "\n==================== %s ====================\n" "$1"; }

json_field() {  # json_field campo  (lee json de stdin, primer match)
  grep -o "\"$1\":\"[^\"]*\"" | head -1 | cut -d'"' -f4
}

product_id() {
  curl -s "$1/products?limit=500" | grep -o "{[^}]*\"sku\":\"$SKU\"[^}]*}" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2
}

qty() {  # qty url product_id campo
  curl -s "$1/inventory/$2" | grep -o "\"$3\":[0-9]*" | head -1 | cut -d: -f2
}

show_stock() {
  local q2
  q2="$(qty "$WH2" "$P2" quantity)"
  if [ -z "$q2" ]; then
    printf "  WH-001: cantidad=%s reservado=%s | WH-002: caida\n" \
      "$(qty "$WH1" "$P1" quantity)" "$(qty "$WH1" "$P1" reserved_quantity)"
  else
    printf "  WH-001: cantidad=%s reservado=%s | WH-002: cantidad=%s reservado=%s\n" \
      "$(qty "$WH1" "$P1" quantity)" "$(qty "$WH1" "$P1" reserved_quantity)" \
      "$q2" "$(qty "$WH2" "$P2" reserved_quantity)"
  fi
}

snapshot() {
  S1Q=$(qty "$WH1" "$P1" quantity); S1R=$(qty "$WH1" "$P1" reserved_quantity)
  S2Q=$(qty "$WH2" "$P2" quantity)
}

create() {  # create cantidad simulate [transfer_id]
  local extra=""
  [ -n "$2" ] && extra=",\"simulate\":\"$2\""
  [ -n "${3:-}" ] && extra="$extra,\"transfer_id\":\"$3\""
  curl -s -X POST "$CENTRAL/transfers" -H 'Content-Type: application/json' \
    -d "{\"source_warehouse\":\"WH-001\",\"destination_warehouse\":\"WH-002\",\"sku\":\"$SKU\",\"quantity\":$1$extra}"
}

status_of() { curl -s "$CENTRAL/transfers/$1" | json_field status; }

wait_status() {  # wait_status id estado segundos
  local i
  for i in $(seq 1 "$3"); do
    [ "$(status_of "$1")" = "$2" ] && return 0
    sleep 1
  done
  return 1
}

history() {
  echo "  historial de $1:"
  curl -s "$CENTRAL/transfers/$1" | grep -o '"status":"[A-Z_]*","detail":"[^"]*"' \
    | sed 's/"status":"\([A-Z_]*\)","detail":"\([^"]*\)"/    \1 - \2/'
}

wait_wh002() {
  local i
  for i in $(seq 1 60); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$WH2/health")" = "200" ] && return 0
    sleep 2
  done
  return 1
}

stop_wh002() { $COMPOSE stop wh002-api-1 wh002-api-2 wh002-api-3 >/dev/null 2>&1; }
start_wh002() { $COMPOSE start wh002-api-1 wh002-api-2 wh002-api-3 >/dev/null 2>&1; wait_wh002; }

result() {  # result nombre condicion(0/1)
  if [ "$2" = "0" ]; then
    echo "  >> OK: $1"
    PASSED=$((PASSED+1))
  else
    echo "  >> FALLO: $1"
    FAILED_TESTS="$FAILED_TESTS\n  - $1"
  fi
}

check_delta() {  # check_delta dq1 dr1 dq2  (cambios esperados)
  local q1 r1 q2
  q1=$(qty "$WH1" "$P1" quantity); r1=$(qty "$WH1" "$P1" reserved_quantity); q2=$(qty "$WH2" "$P2" quantity)
  [ $((q1 - S1Q)) -eq "$1" ] && [ $((r1 - S1R)) -eq "$2" ] && [ $((q2 - S2Q)) -eq "$3" ]
}

# ------------------------------------------------------------------

step "Preparando"
if [ "$(curl -s -o /dev/null -w '%{http_code}' "$CENTRAL/health")" != "200" ]; then
  echo "central-api no responde en $CENTRAL. Corre make up-multi primero." >&2
  exit 1
fi
P1=$(product_id "$WH1"); P2=$(product_id "$WH2")
if [ -z "$P1" ] || [ -z "$P2" ]; then
  echo "No encontre $SKU en WH-001 o WH-002" >&2
  exit 1
fi
available=$(( $(qty "$WH1" "$P1" quantity) - $(qty "$WH1" "$P1" reserved_quantity) ))
if [ "$available" -lt 80 ]; then
  echo "  WH-001 tiene poco stock ($available), agregando 100 unidades"
  curl -s -o /dev/null -X POST "$WH1/inventory/movements" -H 'Content-Type: application/json' \
    -d "{\"product_id\":$P1,\"type\":\"RECEIPT\",\"quantity\":100,\"reference\":\"saga-test\"}"
fi
show_stock

step "Caso del enunciado: 30 unidades de WH-001 a WH-002"
snapshot
r=$(create 30 ""); echo "  POST /transfers -> $r"
id=$(echo "$r" | json_field transfer_id)
wait_status "$id" COMPLETED 30
history "$id"; show_stock
check_delta -30 0 30; result "transferencia normal ($id COMPLETED, -30 / +30)" $?

step "Experimento 1: fallo antes de reservar"
snapshot
id=$(create 5 fail_before_reserve | json_field transfer_id)
wait_status "$id" FAILED 20
history "$id"; show_stock
check_delta 0 0 0; result "fallo antes de reservar ($id FAILED, inventario igual)" $?

step "Experimento 2: fallo despues de reservar"
snapshot
id=$(create 5 fail_after_reserve | json_field transfer_id)
wait_status "$id" RESERVATION_RELEASED 30
history "$id"; show_stock
check_delta 0 0 0; result "fallo despues de reservar ($id compensada, reserva liberada)" $?

step "Experimento 3a: destino caido desde el inicio"
snapshot
stop_wh002
echo "  WH-002 apagada"
id=$(create 5 "" | json_field transfer_id)
wait_status "$id" FAILED 30
history "$id"
echo "  prendiendo WH-002..."
start_wh002; show_stock
check_delta 0 0 0; result "destino caido al inicio ($id FAILED sin mover nada)" $?

step "Experimento 3b: destino se cae con la mercancia en camino"
snapshot
id=$(create 5 pause_before_receive | json_field transfer_id)
wait_status "$id" IN_TRANSIT 30
echo "  $id esta IN_TRANSIT, apagando WH-002"
stop_wh002
wait_status "$id" DESTINATION_PENDING 40
echo "  estado: $(status_of "$id")"
show_stock
echo "  prendiendo WH-002..."
start_wh002
wait_status "$id" COMPLETED 60
history "$id"; show_stock
check_delta -5 0 5; result "destino caido en transito ($id esperó y luego COMPLETED)" $?

step "Experimento 4: mensaje duplicado"
snapshot
tid="TR-DUP-$(date +%s)"
echo "  POST 1 -> $(create 5 "" "$tid")"
echo "  POST 2 -> $(create 5 "" "$tid")"
wait_status "$tid" COMPLETED 30
echo "  reenviando el mismo mensaje a RabbitMQ:"
echo "  $(curl -s -X POST "$CENTRAL/transfers/$tid/resend")"
sleep 5
history "$tid"; show_stock
check_delta -5 0 5; result "mensaje duplicado ($tid se aplico una sola vez)" $?

step "Experimento 5: timeout"
snapshot
id=$(create 5 timeout | json_field transfer_id)
wait_status "$id" COMPLETED 40
history "$id"; show_stock
check_delta -5 0 5; result "timeout ($id reintento sin reservar dos veces)" $?

step "Experimento 6: worker reiniciado"
snapshot
id=$(create 5 slow | json_field transfer_id)
sleep 6
echo "  estado antes de reiniciar: $(status_of "$id")"
docker restart transfer-worker >/dev/null
echo "  transfer-worker reiniciado"
wait_status "$id" COMPLETED 60
history "$id"; show_stock
check_delta -5 0 5; result "worker reiniciado ($id retomo y termino)" $?

step "Resumen"
echo "  experimentos OK: $PASSED de 8"
if [ -n "$FAILED_TESTS" ]; then
  printf "  fallaron:%b\n" "$FAILED_TESTS"
  exit 1
fi
echo "  OK: todos los experimentos de la saga pasaron"
