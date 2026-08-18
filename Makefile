.PHONY: bootstrap dev up down logs migrate seed init-owner solver-poc test test-backend test-frontend test-stack check

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

check:
	cd backend && uv run ruff check app tests migrations
	cd backend && uv run mypy app
	pnpm typecheck
	pnpm build
	pnpm test
	cd backend && uv run pytest
	docker compose config --quiet
	$(MAKE) test-stack
