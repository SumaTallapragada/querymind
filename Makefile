.DEFAULT_GOAL := help
.PHONY: help install run lint format typecheck test check migrate migrate-autogenerate \
        docker-build docker-up docker-down docker-logs docker-clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (including dev) with uv
	uv sync

run: ## Run the API locally with autoreload (requires a reachable Postgres)
	uv run uvicorn querymind.main:app --reload --host 0.0.0.0 --port 8000

lint: ## Lint the codebase with Ruff
	uv run ruff check .

format: ## Format the codebase with Ruff
	uv run ruff format .

typecheck: ## Static type-check with MyPy
	uv run mypy src

test: ## Run the test suite with coverage
	uv run pytest

check: lint typecheck test ## Run lint, typecheck, and test — the full local CI gate

migrate: ## Apply all pending Alembic migrations
	uv run alembic upgrade head

migrate-autogenerate: ## Autogenerate a new Alembic revision from model changes
	uv run alembic revision --autogenerate -m "$(name)"

docker-build: ## Build the application image
	docker compose build

docker-up: ## Start the full stack (app + Postgres) in the foreground
	docker compose up --build

docker-down: ## Stop the stack and remove containers
	docker compose down

docker-logs: ## Tail logs from all services
	docker compose logs -f

docker-clean: ## Stop the stack and remove containers + volumes (deletes DB data)
	docker compose down -v