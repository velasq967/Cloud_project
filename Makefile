.PHONY: up down logs test smoke lint build clean up-multi down-multi ps-multi fault-wh002 load-multi clean-multi

COMPOSE = docker compose --env-file .env -f infrastructure/compose/compose.core.yml
COMPOSE_MULTI = docker compose --env-file .env -f infrastructure/compose/compose.multi.yml

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
	$(COMPOSE_MULTI) up --build -d

down-multi:
	$(COMPOSE_MULTI) down

ps-multi:
	$(COMPOSE_MULTI) ps

fault-wh002:
	bash scripts/fault-test-wh002.sh

load-multi:
	docker run --rm -i --network host -v "$(CURDIR)/load-tests:/load-tests" grafana/k6 \
		run -e SCALE=$${SCALE:-0.1} /load-tests/k6/phase4-multi-warehouse.js

clean-multi:
	$(COMPOSE_MULTI) down -v
