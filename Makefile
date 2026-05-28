# =============================================================================
# Aegis — developer Makefile
# =============================================================================

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Lifecycle ---------------------------------------------------------------

.PHONY: up
up: ## Build + start the full stack
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  backend  -> http://localhost:8000/api/v1/health"
	@echo "  api docs -> http://localhost:8000/docs"
	@echo "  frontend -> http://localhost:5173"

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop the stack AND wipe volumes (destructive — local dev only)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Show running containers
	$(COMPOSE) ps

# --- Backend -----------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply Alembic migrations
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: revision
revision: ## Create a new Alembic revision (msg=...)
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(msg)"

.PHONY: seed
seed: ## Seed dev admin user + default policies (dev only)
	$(COMPOSE) exec backend python -m app.scripts.seed_dev_admin
	$(COMPOSE) exec backend python -m app.scripts.seed_policies

.PHONY: seed-policies
seed-policies: ## Re-seed/upsert the default policy set
	$(COMPOSE) exec backend python -m app.scripts.seed_policies

.PHONY: shell
shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

.PHONY: test
test: ## Run backend pytest suite
	$(COMPOSE) exec backend pytest -v

.PHONY: lint
lint: ## Lint backend (ruff + mypy) and frontend (eslint + tsc)
	$(COMPOSE) exec backend ruff check app tests
	$(COMPOSE) exec backend mypy app
	$(COMPOSE) exec frontend npm run lint
	$(COMPOSE) exec frontend npm run typecheck

.PHONY: fmt
fmt: ## Format backend (ruff format)
	$(COMPOSE) exec backend ruff format app tests
