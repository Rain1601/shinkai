# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Shinkai is a long-running, observable investment-research agent for US equities. It runs in two modes that share the same engine:

- **Mode B — `mode_b_narrative`** (headline use case): theme-driven discovery of *underwater* high-quality companies (e.g. AI infrastructure supply chain). Trace dependency layers from named giants → sub-suppliers → ranked candidates.
- **Mode A — `mode_a_company`**: deep-dive value-investing checklist on candidates surfaced by Mode B (or supplied directly).

Outputs are dual-faced: human-readable dossiers/reports *and* a machine-readable research graph (nodes: Entity/Claim/Evidence/Question/Thesis; edges: structural/evidential/logical/temporal) consumable by other agents.

The authoritative implementation spec is `docs/alignment-v2.md`. Other top-level specs in `docs/` (engineering-framework-v0, agent-loop-and-middle-layer-v0, research-graph-schema-v0, checklists/) are referenced from there. `docs/alignment-v1.md` is historical Q&A and **not authoritative**.

`CHANGELOG.md` at the repo root carries a narrative trace of every milestone, integration, and meaningful update since day 0 (2026-05-31). When you ship something direction-shifting or load-bearing, add an entry at the top — preferred types are `milestone`, `integration`, `feature`, `ui`, `design`, `fix`, `docs`, `decision`.

## Layout

Monorepo: pnpm workspaces (Node 22 / pnpm 9) + a separate uv-managed Python service.

- `services/api/` — FastAPI backend (`shinkai_api` package, Python 3.13, uv). Contains the entire agent harness, persistence, graph, eval, and tools. Run loop is in-process (asyncio); not split into a worker yet.
- `apps/web/` — Next.js 16 / React 19 dashboard (`@shinkai/web`). Pages: `/runs`, `/graph`, `/eval`, `/review`, `/a2a`.
- `packages/shared-types/`, `packages/ui/` — TS workspace placeholders. `make types` is currently a no-op placeholder for an OpenAPI → TS generator.
- `docs/` — design specs; treat `alignment-v2.md` as the source of truth.
- `scripts/dev.sh`, `scripts/smoke.sh` — local dev and end-to-end smoke runner.
- `.shinkai/` — local runtime state (JSON store); never commit.

## Common commands

All day-to-day work goes through the root `Makefile`:

```bash
make setup    # pnpm install + uv sync
make dev      # api :8100 + web :3100 (concurrently)
make api      # api only
make web      # web only
make lint     # ruff (api) + tsc --noEmit (web)
make test     # pytest (api)
make smoke    # full E2E: spawns isolated api :8120 + web :3120, runs an autonomous Mode B run, asserts graph/research/eval shape
```

Targeted commands (when you only need part of the matrix):

```bash
# single backend test
cd services/api && uv run pytest tests/test_autonomous_harness.py -k <name>

# backend lint only
cd services/api && uv run ruff check src tests

# frontend typecheck only (this IS the lint target — there is no eslint)
pnpm --filter @shinkai/web lint

# eval golden cases (CI runs this too)
cd services/api && uv run python -m shinkai_api.eval.cases
```

CI (`.github/workflows/ci.yml`) runs: web typecheck → ruff → pytest → eval cases module → `scripts/smoke.sh`. The smoke test is load-bearing — it asserts concrete shape (`>= 12 candidate_scored events`, `>= 53 graph nodes`, etc.), so harness changes that alter trajectory will break it and the thresholds need updating in lockstep.

## Architecture — what spans multiple files

### Run lifecycle and event stream

A `Run` (`runs/models.py`) is the top-level unit of work. `RunExecutor` (`runs/executor.py`) is a singleton (`default_run_executor`) that:

1. Flips status `created → running` and spawns an asyncio task.
2. Iterates `ShinkaiHarness.run(run)` (an async generator of `AgentEvent`s).
3. For each event: checks pause/abort gates, checks `max_tool_calls` budget, persists via `default_run_store.append_event`, then yields downstream.
4. On FastAPI startup (`main.py`), `recover_active_runs()` re-spawns any run left in `running` state — emits a `run_recovered` event for traceability.

Every state change in the system is expressed as an `AgentEvent` (`schemas/events.py`). The `EventType` literal union is exhaustive — adding a new event type is a contract change touching the harness, the run store, the web `EventStream` component, and often the smoke test. SSE streaming to clients is built directly from this same event log; persistence is idempotent (events are deduplicated on append).

### The harness

`ShinkaiHarness` (`agent/harness.py`) is the planner/reviewer/optimizer loop. For Mode B it walks the planned `SupplyChainLayer`s (proposed by DeepSeek when available, or `AI_SUPPLY_CHAIN_LAYERS` as fallback) through a `FrontierQueue` (`agent/frontier.py`), emitting `frontier_selected` / `candidate_scored` / `claim_created` / `judgment_created` / `hypothesis_created` events and writing into the graph + research stores. It calls `DeepSeekClient` (`llm/deepseek.py`) for planning; **when `SHINKAI_DEEPSEEK_API_KEY` is unset, DeepSeek errors, or its output fails validation, it falls back to deterministic layer expansion** — this is what keeps tests stable and what the smoke script relies on. Don't remove the deterministic path.

### Critic personas (L2)

`scope.critics_enabled: true` runs three deterministic critic personas
(`agent/personas/evaluators.py` — Buffett, short-seller, auditor) against every
`company_dossier_created` event. Each critique is emitted as
`critic_persona_critique` and the trio is aggregated via
`aggregate_critiques` (any `reject` ⇒ reject) into `critic_aggregated`. An
aggregated `reject` applies a `-0.08` confidence penalty to the layer's
hypothesis (`method: critic_aggregated_v0`, recorded in
`confidence_history`). Defaults off so the smoke run stays cheap and
predictable.

V0 evaluators are deterministic rules over `quality_score` /
`underwater_score` / primary-source count, not LLM calls. The
`BUFFETT_PROMPT` / `SHORT_SELLER_PROMPT` / `AUDITOR_PROMPT` templates are
preserved for the V1 swap to LLM-backed critics.

### Discovery mode matrix

`scope.discovery_mode` and `scope.force_llm_planner` decide where the layer list comes from:

| `discovery_mode` | API key set | LLM output valid | Result |
| --- | --- | --- | --- |
| `auto` (default) | yes | yes | LLM layers (`planner_source: deepseek_llm_planner`) |
| `auto` | yes | no | `AI_SUPPLY_CHAIN_LAYERS` (`planner_source: fallback_after_reject`) |
| `auto` | no | — | `AI_SUPPLY_CHAIN_LAYERS` (`planner_source: deterministic_fallback`) |
| `llm_driven` | yes | yes | LLM layers; `planner_source: deepseek_llm_planner` |
| `llm_driven` | yes | no | run fails (`status: failed`, `planner_source: force_llm_fail`) |
| `llm_driven` | no | — | run fails |
| `deterministic` | — | — | `AI_SUPPLY_CHAIN_LAYERS`, LLM never called |

Setting `scope.force_llm_planner: true` on top of `auto` raises the same fail-fast behaviour as `llm_driven`. The harness emits a `planner_proposals` event in every case so the UI can show the chosen source, raw vs validated layer count, sample layer names, and reject reason.

### Tools

`tools/` holds the executable tool surface that the harness can invoke. All tools go through `default_tool_registry` and return `ToolResult`.

| Tool | Backend | Notes |
| --- | --- | --- |
| `web_search` | `market-utils` `SearchEngine` — strategy selected by `SHINKAI_WEB_SEARCH_STRATEGY` | See "Web search strategies" below |
| `web_extract` | direct HTTP + HTML parsing | extracts a compact text excerpt from a URL |
| `ticker_validate` | yfinance + SEC EDGAR `company_tickers.json` fallback | resolves a ticker to sector / industry / business summary and returns `industry_eligible` after the hard filter against `INELIGIBLE_SECTORS` (Healthcare, Real Estate, Financial Services, Utilities, Consumer Defensive, Communication Services) and `INELIGIBLE_INDUSTRIES` (Resorts & Casinos, Lodging, etc.) — catches LLM hallucinations like "ATYR Pharma for HBM" or "BOYD Gaming for liquid cooling" |
| `sec_filings` | SEC EDGAR submissions endpoint (free, requires `User-Agent` header) | pulls recent 10-K / 10-Q filings and returns metadata + primary document URLs ready to become `SourceRef(tier="primary")` |
| `fxbg_search` / `fxbg_paragraphs` / `fxbg_pdf_url` | 发现报告 (fxbaogao) MCP HTTP API at `api.fxbaogao.com/mcp/` — three tools wrapping `search_reports` / `get_paragraphs` / `get_pdf_url`. Requires `SHINKAI_FXBAOGAO_API_KEY` (Premium VIP, `sk-xxx`). `fxbg_search` + `fxbg_paragraphs` are free; `fxbg_pdf_url` consumes 1 download from the 300/month quota. **`fxbg_search` defaults to the MS / GS / Nomura issuer whitelist** (`PREFERRED_ORG_NAMES`) and drops `未知机构` + reports under 3 pages — empirically the highest-density sell-side names with the least rumor noise. Override via `org_names=[...]` or `use_default_orgs=False`. Helper `download_pdf_from_url()` streams the signed CDN URL (`dr.fxbaogao.com`) to disk. Harness does **not** auto-call these in phase 1 — drive via `scripts/fxbg_explore.py` only. |

#### Web search strategies

`web_search` is backed by the in-house `market-utils` `SearchEngine`. `SHINKAI_WEB_SEARCH_STRATEGY` picks the backend; with `auto` it tries `vertex_grounding` → `tavily` → `google` → `duckduckgo` in order of what's configured.

- **`vertex_grounding`** (preferred for new GCP projects): Vertex AI Gemini + `google_search` tool, two-pass (ground → structure into `SearchResult` rows). Verified working end-to-end on 2026-06-17. Requires `SHINKAI_GOOGLE_CLOUD_PROJECT` plus ADC (`gcloud auth application-default login`) or `SHINKAI_GOOGLE_APPLICATION_CREDENTIALS` pointing at a SA JSON with `roles/aiplatform.user` + `roles/serviceusage.serviceUsageConsumer`. Optional `SHINKAI_GOOGLE_CLOUD_LOCATION` (default `us-central1`), `SHINKAI_VERTEX_MODEL` (default `gemini-2.5-flash`). ~$0.04 / search.
- **`tavily`**: requires `SHINKAI_TAVILY_API_KEY`. Structured JSON with score.
- **`google`**: legacy Custom Search JSON API — Google closed CSE to new customers in 2025, only works on grandfathered projects. Do not provision new keys here.
- **`duckduckgo`**: free fallback, no key.

A "premium publisher" strategy is also wired up (Agent Search with `searchLite`, Standard tier — see recent commits and `scripts/provision-premium-data-store.py`); noise domains are pushed to Vertex `exclude_domains` via the bridge.

A run carries a `scope.allow_live_sources` flag — when `false`, tools must serve from cached/stubbed data. Tests and the smoke run set this to `false`; live calls are reserved for explicitly opted-in runs.

SEC EDGAR requires a real User-Agent (`shinkai-research-agent rain@shinkai.local` by default in `tools/ticker_validator.py::SEC_USER_AGENT`). Rate limit is 10 req/s, no API key needed.

### Persistence — Postgres-first with JSON fallback

`persistence/state_store.py` defines `StateStore`, used by `runs/store.py`, `graph/store.py`, `research/store.py`, `checkpoints/store.py`. Default is JSON at `.shinkai/state.json` (override via `SHINKAI_STATE_PATH`). Setting `SHINKAI_DATABASE_URL` switches to Postgres (`persistence/postgres_state.py`); if `SHINKAI_PERSISTENCE_JSON_FALLBACK=true` (default), any Postgres exception transparently falls back to JSON — useful locally, but be aware that this can mask real Postgres breakage in production. Section-keyed saves (`save_section("runs", …)`) are how the stores write back.

### Research graph + research records

Two parallel write surfaces, both populated by the harness:

- `graph/` — typed `Node`/`Edge` model implementing the research-graph-schema-v0 contract. `GraphDelta` events carry diffs.
- `research/` — higher-level domain records (`CandidateCompany`, `Claim`, `Evidence`, `CompanyDossier`, `ResearchTask`, `SourceRef`) with confidence/tier/reliability scoring helpers (`assess_claim_support`, `classify_source_tier`, `source_reliability_score`).

These are not redundant: the graph is the agent-consumable representation, the research records are the human-consumable dossier representation. Changes to one usually require changes to the other.

### Eval

`eval/runner.py` + `eval/cases.py` scores a completed run on process, evidence, reasoning, claim, source-quality, and dossier dimensions. The smoke test asserts these scores are populated. The `cases.py` module is runnable (`python -m shinkai_api.eval.cases`) and gates CI on golden adversarial behavior.

### Access model

`api/auth.py` + `core/auth.py` + `core/config.py` implement two roles. Subscribers (read-only, listed via `SHINKAI_SUBSCRIBER_TOKENS`) can view runs, graph, eval, results. Admins (`SHINKAI_ADMIN_TOKEN`) can create/start/pause/abort/release runs and post A2A messages. The session endpoint returns `capabilities` so the web UI can hide admin controls without separate role-fetching. `auth_required` defaults to `false` for local development.

### Web frontend

App Router under `apps/web/app/`. Cross-page UI lives in `components/portal/` (`PortalShell`, `EventStream`, `GraphPanel`, `RunProgress`, `ActionPanel`, `JudgmentPanel`, `AutonomyPanel`). The `lint` script is `tsc --noEmit` only — there's no ESLint. The web app expects `NEXT_PUBLIC_API_URL` (set by `scripts/dev.sh` and `make web`).

## Conventions worth knowing

- **Ports**: dev uses 8100/3100, smoke uses 8120/3120. Don't hardcode either — read from env (`API_PORT`, `WEB_PORT`).
- **Tests**: `allow_live_sources: false` for deterministic runs. Live-source paths are exercised only via the smoke script or explicit mocked tools.
- **Python style**: ruff `E,F,I,UP,B`, 100-char lines, Python 3.13 syntax (`|` unions, `from __future__ import annotations` is common). Prefer Pydantic models for any API or persisted contract.
- **Commit prefixes**: `feat:`, `fix:`, `test:`, `docs:` (see recent `git log`).
- **Don't commit**: `.shinkai/`, `.env*`, anything containing a DeepSeek key.

## Environment variables (prefix `SHINKAI_`)

| Var | Effect |
| --- | --- |
| `SHINKAI_DEEPSEEK_API_KEY` | Enables real DeepSeek planning; absent = deterministic fallback |
| `SHINKAI_LLM_MODEL` | DeepSeek model (default `deepseek-chat`) |
| `SHINKAI_STATE_PATH` | JSON state file (default `.shinkai/state.json`) |
| `SHINKAI_DATABASE_URL` | Switch to Postgres backing store |
| `SHINKAI_PERSISTENCE_JSON_FALLBACK` | Default `true`; set `false` in prod to fail loudly on DB errors |
| `SHINKAI_AUTH_REQUIRED` / `SHINKAI_ADMIN_TOKEN` / `SHINKAI_SUBSCRIBER_TOKENS` | Access control |
| `SHINKAI_WEB_SEARCH_STRATEGY` | `auto` / `vertex_grounding` / `tavily` / `google` / `duckduckgo` |
| `SHINKAI_GOOGLE_CLOUD_PROJECT` / `SHINKAI_GOOGLE_APPLICATION_CREDENTIALS` / `SHINKAI_GOOGLE_CLOUD_LOCATION` / `SHINKAI_VERTEX_MODEL` | Vertex Grounding config |
| `SHINKAI_TAVILY_API_KEY` | Tavily backend for `web_search` |
| `SHINKAI_FXBAOGAO_API_KEY` | Premium VIP `sk-xxx` key for `fxbg_*` tools (发现报告 MCP) |
| `SHINKAI_FXBAOGAO_ENDPOINT` | Override the fxbaogao MCP endpoint (default `https://api.fxbaogao.com/mcp/`) |
| `NEXT_PUBLIC_API_URL` | Web → API base URL (set by dev scripts) |

## Deployment

Production target is Google Cloud Run via `.github/workflows/deploy-cloud-run.yml` (Workload Identity Federation). Configuration knobs and Secret Manager keys are documented in `docs/deployment-google-cloud.md`. The backend's long-running async run loop is why we deploy as a container — Vercel functions are not viable for the API service. The web app can still deploy to Vercel.
