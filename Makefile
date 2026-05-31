.PHONY: help setup setup-web setup-api dev web api types lint test smoke clean

help:
	@echo "shinkai — make targets"
	@echo "  setup       Install all deps (node + python)"
	@echo "  dev         Run web (3100) and api (8100) in parallel"
	@echo "  web         Run web only"
	@echo "  api         Run api only"
	@echo "  types       Regenerate shared types from FastAPI OpenAPI"
	@echo "  lint        Lint all packages"
	@echo "  test        Run backend tests"
	@echo "  smoke       Run API + Web end-to-end smoke test"
	@echo "  clean       Remove build artifacts and caches"

setup: setup-web setup-api

setup-web:
	pnpm install

setup-api:
	cd services/api && uv sync

dev:
	bash scripts/dev.sh

web:
	WEB_PORT=3100 NEXT_PUBLIC_API_URL=http://localhost:8100 pnpm --filter @shinkai/web dev

api:
	cd services/api && SHINKAI_STATE_PATH="$$(cd ../.. && pwd)/.shinkai/state.json" uv run uvicorn shinkai_api.main:app --reload --port 8100

types:
	bash scripts/gen-types.sh

lint:
	pnpm -r --filter "./apps/**" --filter "./packages/**" lint
	cd services/api && uv run ruff check src tests

test:
	cd services/api && uv run pytest

smoke:
	bash scripts/smoke.sh

clean:
	find . -type d -name node_modules -prune -exec rm -rf {} +
	find . -type d -name .next -prune -exec rm -rf {} +
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
