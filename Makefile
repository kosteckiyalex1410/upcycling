# Developer entry points. See docs/development.md.
SHELL := /bin/bash
PNPM ?= pnpm
PWA := @upcycling/expert-pwa
LOCALE ?= uk

.DEFAULT_GOAL := help
.PHONY: help setup services-up services-down migrate seed-user storage-init storage-sweep \
	dev-api dev-web \
	gen-client contract-check format lint typecheck test test-backend test-web test-e2e \
	build docker-smoke check

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install backend and frontend dependencies from lockfiles
	cd backend && uv sync --locked
	$(PNPM) install --frozen-lockfile

services-up: ## Start PostgreSQL, Mailpit and S3-compatible storage; prepare the bucket
	docker compose up -d --wait
	cd backend && uv run python -m app.cli storage-init

services-down: ## Stop local services (data volume is kept)
	docker compose down

migrate: ## Apply database migrations
	cd backend && uv run alembic upgrade head

seed-user: ## Create the expert account: make seed-user EMAIL=you@example.com [LOCALE=uk]
	@test -n "$(EMAIL)" || (echo "Usage: make seed-user EMAIL=you@example.com [LOCALE=uk]" && exit 1)
	cd backend && uv run python -m app.cli create-user --email "$(EMAIL)" --locale "$(LOCALE)" --if-not-exists

storage-init: ## Create the bucket and its browser-upload CORS rule (idempotent)
	cd backend && uv run python -m app.cli storage-init

storage-sweep: ## Purge deleted/stale photos and unreferenced storage objects
	cd backend && uv run python -m app.cli storage-sweep

dev-api: ## Run the API with reload on :8000
	cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000 --timeout-keep-alive 75

dev-web: ## Run the PWA dev server on :5173 (proxies /api)
	$(PNPM) --filter $(PWA) dev

gen-client: ## Export OpenAPI and regenerate the TypeScript client
	cd backend && uv run python -m scripts.export_openapi ../packages/api-client/openapi.json
	$(PNPM) --filter @upcycling/api-client generate

contract-check: ## Fail if the committed OpenAPI/client is stale
	./scripts/check-contract.sh

format: ## Auto-format backend and frontend
	cd backend && uv run ruff format . && uv run ruff check --fix .
	$(PNPM) format

lint: ## Lint and format checks, locale parity
	cd backend && uv run ruff format --check . && uv run ruff check .
	$(PNPM) format:check
	$(PNPM) --filter $(PWA) check:locales
	$(PNPM) lint

typecheck: ## mypy (strict) and tsc
	cd backend && uv run mypy
	$(PNPM) typecheck

test-backend: ## Backend unit, integration and migration tests (needs services-up)
	cd backend && uv run pytest

test-web: ## Frontend unit tests
	$(PNPM) --filter $(PWA) test

test-e2e: ## Playwright e2e against real API/DB/Mailpit (needs services-up)
	$(PNPM) --filter $(PWA) test:e2e

test: test-backend test-web ## All unit/integration tests

build: ## Production build of the PWA
	$(PNPM) --filter $(PWA) build

docker-smoke: ## Build the backend image and smoke-test it against local PostgreSQL
	docker compose exec -T db createdb -U upcycling upcycling_smoke 2>/dev/null || true
	./scripts/docker-smoke.sh

check: lint typecheck test contract-check build ## Everything CI runs except e2e and docker
