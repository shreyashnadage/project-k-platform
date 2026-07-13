.PHONY: up down logs test lint fmt worker dbt-run dbt-test init init-db clean help

# ─── Infrastructure ─────────────────────��───────────────────
up:  ## Start local dev stack
	docker compose up -d
	@echo "Services starting..."
	@echo "  Postgres:          localhost:5432"
	@echo "  Postgres (AGE):    localhost:5433"
	@echo "  Redpanda (Kafka):  localhost:19092"
	@echo "  Redpanda Console:  localhost:8180"
	@echo "  Temporal:          localhost:7233"
	@echo "  Temporal UI:       localhost:8233"
	@echo "  Keycloak:          localhost:8080"

down:  ## Stop local dev stack
	docker compose down

logs:  ## Tail all service logs
	docker compose logs -f

# ─── Python ─────────────────────────────────────────────────
init:  ## Install Python deps (requires uv)
	uv sync --all-extras
	@echo "Dependencies installed. Run 'make up' to start infra."

test:  ## Run all tests
	uv run pytest tests/ -v --tb=short

test-unit:  ## Run unit tests only
	uv run pytest tests/ -v --tb=short -m "not integration"

test-integration:  ## Run integration tests (requires 'make up')
	uv run pytest tests/ -v --tb=short -m "integration"

lint:  ## Lint + type check
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy libs/ services/ --ignore-missing-imports

fmt:  ## Auto-format
	uv run ruff format .
	uv run ruff check --fix .

# ─── Services ───────────────────────────────────────────────
worker:  ## Start the LA orchestrator Temporal worker
	uv run python -m services.la_orchestrator.worker

gateway:  ## Start the borrower gateway API
	uv run uvicorn services.borrower_gateway.app:app --reload --port 8000

ddp:  ## Start the DDP engine API
	uv run uvicorn services.ddp_engine.app:app --reload --port 8001

# ─── Trust Graph (dbt) ─────────────────────��────────────────
dbt-run:  ## Run dbt models
	cd services/trust-graph && uv run dbt run

dbt-test:  ## Run dbt tests
	cd services/trust-graph && uv run dbt test

dbt-docs:  ## Generate and serve dbt docs
	cd services/trust-graph && uv run dbt docs generate && uv run dbt docs serve

# ─── Topics & Schemas ───────────────────────────��──────────
# ─── Database Migrations ──────────────────────────────────
init-db:  ## Initialize database schema (create tables + run migrations)
	uv run alembic upgrade head
	@echo "Database schema initialized."

migrate:  ## Run Alembic migrations to head
	uv run alembic upgrade head

migrate-down:  ## Rollback one migration
	uv run alembic downgrade -1

migrate-new:  ## Create a new migration (usage: make migrate-new msg="add foo table")
	uv run alembic revision -m "$(msg)"

topics:  ## Create Redpanda topics
	./scripts/create-topics.sh

schemas:  ## Register schemas with Schema Registry
	./scripts/register-schemas.sh

# ─── Brand ─────────────────────────────────────────────────
brand-css:  ## Regenerate back-office CSS from brand.yaml
	uv run python -m brand.generate_css

brand-docs:  ## Render docs/templates/*.md.tmpl into docs/ from brand.yaml
	uv run python -m brand.render_docs

brand-deploy:  ## Build back-office app with latest brand assets and docs
	uv run python -m brand.generate_css
	uv run python -m brand.generate_hooks
	uv run python -m brand.render_docs
	uv run python -m brand.deploy_backoffice_app

# ─── Cleanup ─────────────────────────────────────────────
clean:  ## Nuke volumes and rebuild
	docker compose down -v
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache .mypy_cache

# ─── Help ──────────────────────────��────────────────────────
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
