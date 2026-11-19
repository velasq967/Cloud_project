.PHONY: up down logs test smoke lint build clean up-multi down-multi ps-multi fault-wh002 load-multi clean-multi lb-test wh002-1 wh002-3 load-lb

COMPOSE = docker compose --env-file .env -f infrastructure/compose/compose.core.yml
COMPOSE_MULTI = docker compose --env-file .env -f infrastructure/compose/compose.multi.yml
# k6 corre dentro de la red de docker (en mac --network host no llega a localhost)
K6 = docker run --rm -i --network warehouse-multi_default -v "$(CURDIR)/load-tests:/load-tests" grafana/k6 run

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

test:
	$(COMPOSE) exec api pytest -q

smoke:
	powershell -ExecutionPolicy Bypass -File ./scripts/smoke-test.ps1

lint:
	ruff check .

build:
	$(COMPOSE) build --no-cache

clean:
	$(COMPOSE) down -v

# fase 4
up-multi:
	$(COMPOSE_MULTI) up --build -d --remove-orphans

down-multi:
	$(COMPOSE_MULTI) down --remove-orphans

ps-multi:
	$(COMPOSE_MULTI) ps

fault-wh002:
	bash scripts/fault-test-wh002.sh

load-multi:
	$(K6) -e SCALE=$${SCALE:-0.1} -e WH1=http://wh001-api:8000 -e WH2=http://wh002-lb \
		-e WH3=http://wh003-api:8000 /load-tests/k6/phase4-multi-warehouse.js

clean-multi:
	$(COMPOSE_MULTI) down -v

# fase 5
lb-test:
	bash scripts/lb-test.sh

wh002-1:
	$(COMPOSE_MULTI) stop wh002-api-2 wh002-api-3

wh002-3:
	$(COMPOSE_MULTI) start wh002-api-2 wh002-api-3

load-lb:
	$(K6) -e RATE=$${RATE:-200} -e WH2=http://wh002-lb /load-tests/k6/phase5-wh002.js
