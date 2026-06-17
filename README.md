# shinkai

Long-running investment research agent for discovering themes and performing deep company analysis on under-covered high-quality candidates.

## Structure

```text
shinkai/
├── apps/
│   └── web/                 # Next.js frontend skeleton
├── services/
│   └── api/                 # FastAPI backend and shinkai harness skeleton
├── packages/
│   ├── shared-types/        # TypeScript API/domain types
│   └── ui/                  # Shared UI package placeholder
├── docs/                    # Product, architecture, graph, and checklist specs
├── scripts/                 # Dev and type-generation scripts
└── Makefile                 # Unified command entrypoint
```

## Development

Prerequisites: Node 22+, pnpm 9+, Python 3.13+, and uv.

```bash
make setup
make dev
```

Useful commands:

```bash
make api      # FastAPI on :8100
make web      # Next.js on :3100
make types    # placeholder for OpenAPI -> TS generation
make lint
make test
make smoke    # starts isolated API/Web ports and runs an end-to-end check
```

## Current Scope

The repository now contains a runnable V1.0 vertical slice:

- asynchronous run execution with live server-sent events
- review/optimize-oriented shinkai harness for AI supply-chain discovery
- bounded autonomous child-run spirals for self-iteration
- DeepSeek frontier-planning integration with deterministic fallback
- frontier queue selection with explicit planner, reviewer, and optimizer trace events
- web search/extract tool events plus structured source, evidence, claim, candidate, and task records
- Mode A company dossiers with checks, risks, catalysts, and invest/watch/reject decisions
- source tiering, primary-source flags, citation locators, and refuting-evidence search for claim review
- startup recovery for running jobs, idempotent event writes, and tool-call budget guards
- Postgres-ready persistence with JSON fallback for local runs, events, research state, and graphs
- eval reports for process, evidence, reasoning, and discovery quality
- web dashboards for runs, graph, eval, review, and A2A views

The next slices are durable worker scheduling, stronger eval sets, and deeper Mode A company-analysis dossiers.

## DeepSeek Runtime

The autonomous discovery harness can use DeepSeek directly for frontier planning.
Keep the API key out of repo files:

```bash
export SHINKAI_DEEPSEEK_API_KEY="..."
export SHINKAI_LLM_MODEL="deepseek-chat"
make api
```

Without the key, the harness falls back to deterministic supply-chain layers.

## Web Search Runtime

The `web_search` tool supports four backends via `SHINKAI_WEB_SEARCH_STRATEGY`,
all routed through the [`market-utils`](https://github.com/Rain1601/market-utils)
package:

1. **`vertex_grounding`** — Vertex AI Gemini + Google Search Grounding. This is
   the supported successor to the legacy Custom Search JSON API (which Google
   closed to new GCP projects in 2025). Recommended for any GCP project created
   after that cutoff.
2. **`tavily`** — Tavily search API (fast, cheap, good for news).
3. **`google`** — Legacy Google Custom Search JSON API. Only works on
   grandfathered customers/projects.
4. **`duckduckgo`** — Free fallback, no key required.

To use Vertex Grounding (recommended for new deployments):

```bash
# Service account JSON with roles/aiplatform.user + roles/serviceusage.serviceUsageConsumer
export SHINKAI_GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa.json"
export SHINKAI_GOOGLE_CLOUD_PROJECT="your-gcp-project"
export SHINKAI_GOOGLE_CLOUD_LOCATION="us-central1"
export SHINKAI_VERTEX_MODEL="gemini-2.5-flash"
export SHINKAI_WEB_SEARCH_STRATEGY="vertex_grounding"
make api
```

When `allow_live_sources=true`, the harness will call `web_search` and
`web_extract`. With `SHINKAI_WEB_SEARCH_STRATEGY=auto`, Shinkai picks the first
configured backend in this order: `vertex_grounding` → `tavily` → `google`
→ `duckduckgo`.

## Local State

`make dev` writes run/event/graph state to `.shinkai/state.json`. Override it with:

```bash
export SHINKAI_STATE_PATH="/tmp/shinkai-state.json"
```

For Postgres-backed state, set:

```bash
export SHINKAI_DATABASE_URL="postgresql://user:pass@host:5432/shinkai"
export SHINKAI_PERSISTENCE_JSON_FALLBACK=true
```

Do not commit `.shinkai/` or any environment file containing secrets.

## Access Model

Ordinary users can view published results and the agent running process. Admin users can create,
start, pause, abort, release, and send A2A messages. The API session endpoint returns explicit
capabilities so a future subscription role can expand read scope without granting admin controls.

## Verification

Run the full local verification set:

```bash
pnpm --filter @shinkai/web lint
cd services/api && uv run ruff check src tests && uv run pytest
bash scripts/smoke.sh
```

The smoke test verifies:

- API health
- local CORS preflight
- Web `/runs` page availability
- asynchronous autonomous Mode B run creation and execution
- graph output with candidate/evidence/claim nodes and edges
- eval output

## Deployment

CI runs on GitHub Actions through `.github/workflows/ci.yml`. Production deployment is defined in
`.github/workflows/deploy-cloud-run.yml` and targets Google Cloud Run using Workload Identity
Federation. See `docs/deployment-google-cloud.md` for required Google Cloud variables, Secret
Manager secrets, and the read-only/user vs admin access model.
