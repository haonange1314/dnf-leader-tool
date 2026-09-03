.PHONY: bootstrap dev up down logs migrate seed init-owner solver-poc test test-backend test-frontend test-stack test-e2e test-performance test-quality test-deepseek-live prod-config prod-up prod-down prod-logs prod-smoke backup restore check release-check

export UV_CACHE_DIR ?= $(CURDIR)/.uv-cache

bootstrap:
	@test -f .env || cp .env.example .env
	pnpm install --frozen-lockfile
	cd backend && uv sync --frozen

dev:
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api web db

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.cli seed

init-owner:
	cd backend && uv run python -m app.cli init-owner

solver-poc:
	cd backend && uv run python -m app.solver.poc

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	pnpm test

test-stack:
	sh scripts/test-stack.sh

test-e2e:
	sh scripts/test-e2e.sh

test-performance:
	cd backend && uv run pytest -m performance -s

test-quality:
	cd backend && uv run pytest -m quality -s

test-deepseek-live:
	cd backend && uv run python -m app.cli check-deepseek

prod-config:
	docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml config --quiet

prod-up: prod-config
	docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up --build -d --wait

prod-down:
	docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml down

prod-logs:
	docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml logs -f gateway api web db

prod-smoke:
	@test -n "$(PUBLIC_BASE_URL)" || (echo "PUBLIC_BASE_URL is required" >&2; exit 1)
	PUBLIC_BASE_URL="$(PUBLIC_BASE_URL)" sh scripts/check-production-health.sh

backup:
	sh scripts/backup-db.sh

restore:
	@test -n "$(BACKUP_FILE)" || (echo "BACKUP_FILE is required" >&2; exit 1)
	CONFIRM_RESTORE=dnf_leader sh scripts/restore-db.sh "$(BACKUP_FILE)"

check:
	cd backend && uv run ruff check app tests migrations
	cd backend && uv run mypy app
	pnpm typecheck
	pnpm build
	pnpm test
	cd backend && uv run pytest
	docker compose config --quiet
	$(MAKE) test-stack
	$(MAKE) test-performance
	$(MAKE) test-e2e

release-check: prod-config check
	@echo "release acceptance: local checks and production configuration passed"
