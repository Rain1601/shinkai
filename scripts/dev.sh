#!/usr/bin/env bash
set -euo pipefail

API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:${API_PORT}}"
export WEB_PORT
export SHINKAI_STATE_PATH="${SHINKAI_STATE_PATH:-${PWD}/.shinkai/state.json}"

pnpm exec concurrently \
  "pnpm --filter @shinkai/web dev" \
  "cd services/api && uv run uvicorn shinkai_api.main:app --reload --port ${API_PORT}"
