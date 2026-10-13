# Convenience wrapper around docker compose. Raw commands are in the README,
# so this file is optional (and works from Git Bash / WSL / macOS / Linux).

COMPOSE ?= docker compose

.PHONY: up down rebuild logs migrate seed test api-shell ext fe

up:            ## Build and start the whole stack
	$(COMPOSE) up -d --build

down:          ## Stop the stack (keeps the Postgres volume)
	$(COMPOSE) down

rebuild:       ## Stop and wipe all data volumes
	$(COMPOSE) down -v

logs:          ## Tail api + worker logs
	$(COMPOSE) logs -f api worker

migrate:       ## Re-run migrations explicitly (api already runs them on start)
	$(COMPOSE) run --rm migrate

seed:          ## Load demo users, policies and retention defaults
	$(COMPOSE) --profile tools run --rm seed

test:          ## Backend test suite (fast: SQLite in-memory, no ML deps)
	$(COMPOSE) run --rm api pytest -q

api-shell:     ## Shell inside the api container
	$(COMPOSE) run --rm api bash

ext:           ## Build the browser extension into extension/dist
	cd extension && npm install && npm run build

fe:            ## Run the dashboard in dev mode (hot reload on :5173)
	cd frontend && npm install && npm run dev
