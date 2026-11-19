#!/usr/bin/env bash
# Fase 5: muestra el balanceo entre las 3 replicas de WH-002 y que
# el sistema sigue respondiendo si se apaga una.
# Uso: make up-multi && bash scripts/lb-test.sh

set -uo pipefail

COMPOSE="docker compose --env-file .env -f infrastructure/compose/compose.multi.yml"
LB="http://localhost:8002"

step() { printf "\n==> %s\n" "$1"; }

instance() {
  curl -s -o /dev/null -D - --max-time 3 "$LB/inventory/1" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-instance-id"{print $2}'
}

step "1. Repartiendo 9 requests"
for i in $(seq 1 9); do
  echo "request $i -> $(instance)"
done

step "2. Apagando wh002-api-2 mientras llegan requests"
ok=0
err=0
start=$(date +%s)
stopped=0
started=0
while [ $(( $(date +%s) - start )) -lt 20 ]; do
  elapsed=$(( $(date +%s) - start ))
  if [ $elapsed -ge 5 ] && [ $stopped -eq 0 ]; then
    $COMPOSE stop wh002-api-2 >/dev/null 2>&1 &
    echo "  (segundo $elapsed: apagando wh002-api-2)"
    stopped=1
  fi
  if [ $elapsed -ge 14 ] && [ $started -eq 0 ]; then
    $COMPOSE start wh002-api-2 >/dev/null 2>&1 &
    echo "  (segundo $elapsed: prendiendo wh002-api-2)"
    started=1
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$LB/inventory/1")"
  if [ "$code" = "200" ]; then ok=$((ok+1)); else err=$((err+1)); fi
  sleep 0.1
done
wait

echo "requests OK: $ok"
echo "requests con error: $err"

step "3. Reparto despues de que wh002-api-2 volvio"
sleep 5
for i in $(seq 1 6); do
  echo "request $i -> $(instance)"
done

echo ""
if [ $err -eq 0 ]; then
  echo "OK: WH-002 siguio respondiendo con una replica apagada"
else
  echo "Hubo $err errores de $((ok+err)) requests" >&2
  exit 1
fi
