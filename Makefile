.PHONY: up down logs test smoke lint build clean

COMPOSE = docker compose --env-file .env -f infrastructure/compose/compose.core.yml

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
