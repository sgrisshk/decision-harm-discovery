SHELL := /bin/sh

.PHONY: setup dev test lint typecheck format db-migrate db-upgrade fixture benchmark export-public-benchmark blind-workspace blind-prepare blind-verify blind-shell blind-freeze blind-status analytical-dataset temporal-splits check-data docker-build

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

benchmark:
	uv run python scripts/generate_synthetic_benchmark.py

export-public-benchmark: temporal-splits
	test -n "$(destination)"
	uv run python scripts/prepare_blind_workspace.py "$(destination)"

blind-workspace: export-public-benchmark

BLIND_RUNS_ROOT ?= /tmp/policy-blind-runs
BLIND_AGENT_IMAGE ?= policy-blind-agent:local
AGENT ?= external-cli
BLIND_NETWORK ?= none

blind-prepare:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli prepare --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)"

blind-verify:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli verify --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)"

blind-shell:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli launch --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --agent "$(AGENT)" --image "$(BLIND_AGENT_IMAGE)" --network "$(BLIND_NETWORK)"

blind-freeze:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli freeze --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)"

blind-status:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli status --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)"

analytical-dataset: benchmark
	uv run python scripts/build_synthetic_analytical_dataset.py

temporal-splits: analytical-dataset
	uv run python scripts/build_temporal_splits.py

check-data:
	uv run python scripts/check_repository_data.py

docker-build:
	docker build -f infra/docker/api.Dockerfile -t policy-api:$${GIT_SHA:-local} .
	docker build -f infra/docker/web.Dockerfile -t policy-web:$${GIT_SHA:-local} .
