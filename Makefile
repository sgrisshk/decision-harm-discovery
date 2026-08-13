SHELL := /bin/sh

.PHONY: setup dev test lint typecheck format db-migrate db-upgrade fixture docker-build

setup:
	test -f .env || cp .env.example .env
	uv sync --all-groups
	pnpm install --frozen-lockfile

dev:
	docker compose up --build

test:
	uv run pytest

lint:
	uv run ruff check .
	pnpm --filter web lint

typecheck:
	uv run pyright
	pnpm --filter web typecheck

format:
	uv run ruff format .
	pnpm exec prettier --write "apps/web/**/*.{ts,tsx,css,json}" "*.{json,yaml,yml}"

db-migrate:
	cd apps/api && uv run alembic revision --autogenerate -m "$(m)"

db-upgrade:
	cd apps/api && uv run alembic upgrade head

fixture:
	uv run python scripts/generate_synthetic_fixture.py

docker-build:
	docker build -f infra/docker/api.Dockerfile -t policy-api:$${GIT_SHA:-local} .
	docker build -f infra/docker/web.Dockerfile -t policy-web:$${GIT_SHA:-local} .
