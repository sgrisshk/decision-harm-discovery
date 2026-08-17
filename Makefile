SHELL := /bin/sh

.PHONY: setup dev test lint typecheck format db-migrate db-upgrade fixture benchmark export-public-benchmark blind-workspace blind-key-init blind-image blind-rehearsal blind-issue blind-prepare blind-verify blind-shell blind-freeze blind-status analytical-dataset temporal-splits check-data docker-build

setup:
	test -f .env || cp .env.example .env
	uv sync --all-groups
	pnpm install --frozen-lockfile

dev:
	docker compose up --build

test:
	uv run pytest
	pnpm --filter web test

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
	uv run python scripts/prepare_blind_workspace.py "$(destination)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)"

blind-workspace: export-public-benchmark

BLIND_RUNS_ROOT ?= /tmp/policy-blind-runs
BLIND_EVALUATOR_KEY_FILE ?= /tmp/policy-blind-evaluator/signing.key
BLIND_AGENT_IMAGE_TAG ?= policy-blind-agent:deterministic-local
BLIND_AGENT_IMAGE ?= policy-blind-agent@sha256:9ad6e1a78ca41a7c04895d1d99c7775e77fc2c8fbb4f23cee268ed04534c7c9b
AGENT ?= deterministic
BLIND_NETWORK ?= none

blind-key-init:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli init-key --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)"

blind-image:
	docker build --provenance=false --sbom=false -f infra/docker/blind-agent.Dockerfile -t "$(BLIND_AGENT_IMAGE_TAG)" .
	@built="$$(docker image inspect --format '{{.Id}}' "$(BLIND_AGENT_IMAGE_TAG)")"; \
	pinned="$(BLIND_AGENT_IMAGE)"; \
	pinned="$${pinned#*@}"; \
	if [ "$$built" != "$$pinned" ]; then \
		echo "blind-image: built image digest ($$built) does not match the pinned BLIND_AGENT_IMAGE ($$pinned)." >&2; \
		echo "blind-image: this is expected after any Dockerfile/base-image/apt-package change, but it means every reproducibility and digest-pin guarantee (tools/blind_agent/core.py resolve_image) is void until re-pinned." >&2; \
		echo "blind-image: review the diff, confirm it is intentional, then update BLIND_AGENT_IMAGE here and in TASKS.md/memory/HANDOFFS.md to $$built and re-run make blind-rehearsal before issuing an official run." >&2; \
		exit 1; \
	fi

blind-rehearsal:
	@test -n "$(BLIND_AGENT_IMAGE)"
	uv run python -m tools.blind_agent.rehearsal --image "$(BLIND_AGENT_IMAGE)"

blind-issue:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli issue --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)" --agent "$(AGENT)" --image "$(BLIND_AGENT_IMAGE)"

blind-prepare:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli prepare --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)" --agent "$(AGENT)" --image "$(BLIND_AGENT_IMAGE)"

blind-verify:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli verify --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)"

blind-shell:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli launch --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)" --agent "$(AGENT)" --image "$(BLIND_AGENT_IMAGE)" --network "$(BLIND_NETWORK)"

blind-freeze:
	test -n "$(RUN)"
	uv run python -m tools.blind_agent.cli freeze --run "$(RUN)" --runs-root "$(BLIND_RUNS_ROOT)" --key-file "$(BLIND_EVALUATOR_KEY_FILE)"

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
