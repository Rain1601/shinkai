#!/usr/bin/env bash
set -euo pipefail

API_PORT="${API_PORT:-8120}"
WEB_PORT="${WEB_PORT:-3120}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="http://localhost:${API_PORT}"
WEB_URL="http://localhost:${WEB_PORT}"
STATE_PATH="/tmp/shinkai-smoke-state-${API_PORT}.json"
rm -f "${STATE_PATH}"

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then kill "${API_PID}" >/dev/null 2>&1 || true; fi
  if [[ -n "${WEB_PID:-}" ]]; then kill "${WEB_PID}" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

cd "${ROOT_DIR}/services/api"
SHINKAI_STATE_PATH="${STATE_PATH}" uv run uvicorn shinkai_api.main:app --port "${API_PORT}" \
  > /tmp/shinkai-api-smoke.log 2>&1 &
API_PID=$!

cd "${ROOT_DIR}"
NEXT_PUBLIC_API_URL="${API_URL}" pnpm --filter @shinkai/web exec next dev --port "${WEB_PORT}" \
  > /tmp/shinkai-web-smoke.log 2>&1 &
WEB_PID=$!

for _ in {1..60}; do
  if curl -fsS "${API_URL}/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
curl -fsS "${API_URL}/health" >/dev/null

for _ in {1..40}; do
  if curl --max-time 20 -fsS "${WEB_URL}/runs" >/dev/null 2>&1; then break; fi
  if ! kill -0 "${WEB_PID}" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl --max-time 20 -fsS "${WEB_URL}/runs" >/tmp/shinkai-runs-page.html 2>/dev/null; then
  # Next dev allows only one server per project. If another shinkai dev server
  # already owns the lock, reuse the conventional local dev port for page smoke.
  WEB_URL="http://localhost:3100"
  curl --max-time 20 -fsS "${WEB_URL}/runs" >/tmp/shinkai-runs-page.html
fi

curl -fsS -X OPTIONS "${API_URL}/api/v1/runs" \
  -H "Origin: ${WEB_URL}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  >/tmp/shinkai-cors.txt

run_json="$(curl -fsS -X POST "${API_URL}/api/v1/runs" \
  -H "Content-Type: application/json" \
  -d '{"mode":"mode_b_narrative","anchor":"Autonomous Discovery","scope":{"objective":"discover AI supply-chain key companies","allow_live_sources":false},"budget":{"max_wall_time_minutes":120,"max_tool_calls":80}}')"
run_id="$(RUN_JSON="${run_json}" python3 - <<'PY'
import json
import os
print(json.loads(os.environ["RUN_JSON"])["id"])
PY
)"

curl -fsS -X POST "${API_URL}/api/v1/runs/${run_id}/start" >/tmp/shinkai-smoke-start.json

for _ in {1..120}; do
  curl -fsS "${API_URL}/api/v1/runs/${run_id}" >/tmp/shinkai-smoke-run.json
  status="$(python3 - <<'PY'
import json

with open("/tmp/shinkai-smoke-run.json") as f:
    print(json.load(f)["status"])
PY
)"
  if [[ "${status}" == "completed" || "${status}" == "failed" || "${status}" == "aborted" ]]; then
    break
  fi
  sleep 0.5
done

curl -fsS "${API_URL}/api/v1/runs/${run_id}/graph" >/tmp/shinkai-smoke-graph.json
curl -fsS "${API_URL}/api/v1/runs/${run_id}/research" >/tmp/shinkai-smoke-research.json
curl -fsS "${API_URL}/api/v1/eval/runs/${run_id}" >/tmp/shinkai-smoke-eval.json
curl -fsS "${API_URL}/api/v1/results" >/tmp/shinkai-smoke-results.json
curl -fsS "${API_URL}/api/v1/runs/${run_id}/result" >/tmp/shinkai-smoke-result.json

python3 - <<'PY'
import json

with open("/tmp/shinkai-smoke-run.json") as f:
    run = json.load(f)
with open("/tmp/shinkai-smoke-graph.json") as f:
    graph = json.load(f)
with open("/tmp/shinkai-smoke-research.json") as f:
    research = json.load(f)
with open("/tmp/shinkai-smoke-eval.json") as f:
    report = json.load(f)
with open("/tmp/shinkai-smoke-results.json") as f:
    results = json.load(f)
with open("/tmp/shinkai-smoke-result.json") as f:
    result = json.load(f)

events = run["events"]
assert run["status"] == "completed", run["status"]
assert events[-1]["type"] == "done"
assert sum(1 for event in events if event["type"] == "candidate_scored") >= 12
assert len(graph["nodes"]) >= 50
assert len(graph["edges"]) >= 50
assert len(research["claims"]) >= 16
assert len(research["candidates"]) >= 11
assert len(research["dossiers"]) >= 12
assert len(research["tasks"]) >= 16
assert report["process_score"] is not None
assert report["discovery_score"] is not None
assert report["claim_score"] is not None
assert report["source_quality_score"] is not None
assert report["candidate_dossier_score"] is not None
assert results and results[0]["run_id"] == run["id"]
assert result["metrics"]["claims"] >= 16
assert result["companies"]
print(
    "smoke ok:",
    f"run={run['id']}",
    f"events={len(events)}",
    f"nodes={len(graph['nodes'])}",
    f"edges={len(graph['edges'])}",
    f"process={report['process_score']}",
    f"claim={report['claim_score']}",
)
PY
