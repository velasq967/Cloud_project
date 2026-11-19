#!/usr/bin/env bash
# Apaga WH-002 y revisa que WH-001 y WH-003 sigan funcionando
# Uso: make up-multi && bash scripts/fault-test-wh002.sh
set -uo pipefail

COMPOSE="docker compose --env-file .env -f infrastructure/compose/compose.multi.yml"
# sin declare -A porque el bash de mac (3.2) no lo soporta
api_url() {
  case "$1" in
    WH-001) echo "http://localhost:8001" ;;
    WH-002) echo "http://localhost:8002" ;;
    WH-003) echo "http://localhost:8003" ;;
  esac
}

step() { printf "\n==> %s\n" "$1"; }

check() {
  local wh="$1" url
  url="$(api_url "$1")"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url/health")"
  printf "%-7s /health -> %s\n" "$wh" "$code"
  [ "$code" = "200" ]
}

movement() {
  local wh="$1" url
  url="$(api_url "$1")"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 -X POST "$url/inventory/movements" \
    -H 'Content-Type: application/json' \
    -H "X-Correlation-ID: fault-test-$wh-$(date +%s)" \
    -d '{"product_id": 1, "type": "RECEIPT", "quantity": 1, "reference": "fault-test"}')"
  printf "%-7s POST /inventory/movements -> %s\n" "$wh" "$code"
  [[ "$code" =~ ^2 ]]
}

step "1. Estado inicial"
for wh in WH-001 WH-002 WH-003; do check "$wh"; done

step "2. Apagando WH-002 (api + db)"
$COMPOSE stop wh002-api wh002-db >/dev/null
sleep 2

step "3. WH-002 caida, probando WH-001 y WH-003"
failures=0
check WH-002 && { echo "ERROR: WH-002 deberia estar caida"; failures=$((failures+1)); }
for wh in WH-001 WH-003; do
  check "$wh"    || failures=$((failures+1))
  movement "$wh" || failures=$((failures+1))
done

step "4. Levantando WH-002 otra vez"
$COMPOSE start wh002-db wh002-api >/dev/null
for i in $(seq 1 30); do
  check WH-002 >/dev/null 2>&1 && break
  sleep 2
done
check WH-002 || failures=$((failures+1))

echo
if [ "$failures" -eq 0 ]; then
  echo "OK: WH-001 y WH-003 siguieron funcionando con WH-002 caida"
else
  echo "FALLARON $failures pruebas" >&2
  exit 1
fi
