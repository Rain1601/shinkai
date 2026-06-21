# Agent Tier Progression V0

> Roadmap for evolving shinkai's industry-graph agent from Tier 1 (reactive)
> through Tier 2 (proactive discovery) to Tier 3 (theme-driven cascade).
> Status: V0 specification. Tier 1 is implemented (see
> ``services/api/src/shinkai_api/industry_graph/agent_loop.py`` and
> ``docs/industry-graph-schema-v0.md``); Tier 2 and Tier 3 are planned.

---

## 0. Definitions

### 0.1 What makes something a "real agent"?

Five orthogonal dimensions; we score each tier against them:

| Dimension | Question |
|---|---|
| **Trigger** | Who or what initiates an action? |
| **Goal-setting** | Who defines the goal? |
| **Perception** | How does the agent observe the world? |
| **Action** | How does the agent change the world? |
| **Termination** | When does it stop? |

The number of *external* answers (user, fixed program) versus *internal*
answers (the agent itself) determines the tier.

---

## 1. Tier 1 · Reactive (implemented)

User says what to do; the agent figures out how.

### 1.1 Mechanics

| Dimension | Tier 1 implementation |
|---|---|
| Trigger | User prompt (one per session) |
| Goal-setting | User-supplied task string |
| Perception | Query tools over the in-memory index |
| Action | Write tools committing through ``IndustryGraphStore`` |
| Termination | Agent emits ``{"tool": "done"}`` or hits ``max_turns`` |

### 1.2 Observed autonomy

Real Tier-1 agency demonstrated in the smoke runs:
- **Self-exploration before writing** (calls ``find_*`` repeatedly before any
  ``add_*`` / ``upsert_*``).
- **Self-correction**: when ``get_entity("co:TSMC")`` returned ``ERROR: No
  entity``, the loop switched to ``find_entity("TSMC")`` and discovered the
  real id ``co:2330.TW``.
- **Open-ended choice within goal**: given "find an anchor with fewer
  bottlenecks than NVDA and add a geopolitical risk", the agent ran two
  ``find_bottlenecks`` queries, computed the comparison, picked AMD, and
  generated a US-export-control risk from its own world knowledge.

### 1.3 Known weaknesses (the Tier 1.5 polish list)

| Failure mode | Example | Mitigation |
|---|---|---|
| Repeats the same query forever | E2E #1: 12× ``find_entity`` with the same args | Detect repeated calls in the dispatcher and surface "you ran this already" as the tool result. Optionally rotate the system prompt with a "next step is action, not query" nudge after N consecutive query turns. |
| Forgets to call ``register_source`` | All write tools then complain about missing ``source_ref`` | Auto source_id chaining already exists; extend it to auto-call ``register_source("AGENT", "Agent session <id>")`` on the first write if the session hasn't done so. |
| Loses thread when results are large | Long ``get_entity`` responses crowd out earlier messages | Tighten ``_truncate`` and start summarising older turns into a single system note ("by turn 6 you had explored: …") |
| Never emits ``done`` | Loop ends on ``max_turns`` with the work already finished | Strengthen the ``done`` clause in the system prompt; add a per-turn reminder when ``len(pending) == 0`` after a snapshot. |
| Wrong schema shape | ``stocks_to_watch`` arrives as ``[str]`` not ``[{ticker,...}]`` | Add Pydantic re-validation inside the write tools so the LLM gets a structured ToolResult error pointing at the offending field. |

Tier 1.5 is the next concrete iteration; no new architecture required.

---

## 2. Tier 2 · Proactive Discovery (planned)

The system itself decides when to act and what to look for. The user need not
prompt every session.

### 2.1 Mechanics

| Dimension | Tier 2 design |
|---|---|
| Trigger | Cron schedule (e.g., daily), graph-state event (e.g., new SEC 13F filed), or coverage shortfall against a reference set |
| Goal-setting | A standing policy (e.g., "ensure the graph covers all S&P 500 members") + auto-derived sub-goals (e.g., "co:XYZ is missing → analyse it") |
| Perception | Tier 1 query tools + new "external scanners" (web search, SEC filings, IPO calendars) |
| Action | Tier 1 write tools (called by spawned Tier 1 sessions) |
| Termination | Per-sub-task: same as Tier 1; per-policy: when coverage ≥ threshold or budget exhausted |

### 2.2 Components to build

```
[Trigger layer]
├── cron: daily scan
├── event listener: new filings / news
└── coverage monitor: graph vs reference list

         ↓

[Discovery layer]
├── tool: web_search_giants(category, count)
├── tool: sec_filings_recent(form_type, date_from)
├── tool: news_scan(query, date_range)
└── gap_detector(reference_list, current_graph) → missing[]

         ↓

[Orchestrator]
For each missing entity:
   1. Spawn a Tier 1 ``AgentLoop`` with task =
      "Analyse <entity> and integrate into the graph."
   2. Collect results, commit snapshot per batch.

         ↓

[Policy state]
├── reference lists (S&P 500, Nasdaq 100, top unicorns)
├── last-seen cursor per source (resume from)
└── coverage metric (entities-known / entities-expected)
```

### 2.3 Missing pieces (relative to Tier 1)

- ❌ Cron / event scheduler (could borrow shinkai's existing
  ``runs/executor.py`` task spawn pattern)
- ❌ External-data tools that return *lists*, not free-text
  (``web_search_giants`` style)
- ❌ Gap detector — diff a reference list against ``IndexLayer.by_kind["Company"]``
- ❌ Orchestrator that spawns Tier 1 sessions and tracks their state
- ❌ Policy persistence (where do reference lists live? probably under
  ``.shinkai/industry_graph/policies/``)

### 2.4 Open questions

- How to bound runaway spawning (e.g., a scanner reports 500 new tickers)?
- How to dedupe overlapping sub-tasks (two scanners both flag the same gap)?
- Should the orchestrator itself be an LLM agent ("supervisor"), or a
  deterministic Python loop with rule-based scheduling?
- Where should we record the policy that triggered each sub-task (so we can
  audit "why did the agent analyse XYZ on 2026-07-01")?

---

## 3. Tier 3 · Theme-driven Cascade (planned)

The user gives a *theme* (e.g., "AI Infrastructure", "Data Center Power",
"Robotics"). The agent expands it into a saturated subgraph.

### 3.1 Mechanics

| Dimension | Tier 3 design |
|---|---|
| Trigger | A theme seed (user-supplied or Tier 2 generated) |
| Goal-setting | "Cover the theme until coverage criteria are met" |
| Perception | Tier 1 + Tier 2 tools; additionally a "what's missing in this theme" introspection |
| Action | Tier 1 write tools, plus a ``cascade_step`` meta-tool that requeues children |
| Termination | Coverage metric reaches threshold, or N consecutive cascade steps return no new entities, or budget exhausted |

### 3.2 The cascade loop

```
Input theme  ─→  th:AI_Infrastructure

Step 1. Decompose theme
   LLM call: "What are the L2/L3 sub-themes under AI Infrastructure?"
   → ["GPU", "ASIC", "HBM", "CoWoS", "Optical/CPO", "Power", "Liquid Cooling", ...]

Step 2. For each sub-theme, discover companies
   Tier 1 agent task: "List the dominant companies in <sub-theme>; upsert
   any not yet in the graph."
   → adds Company entities + uses_tech relations

Step 3. For each new company, run supply-chain analysis
   Tier 1 agent task: "Build the upstream supply chain of <co:XYZ>; add
   suppliers / Bottlenecks / KeyDataPoints; do not exceed 8 turns."
   → adds Company / supplies_to / Bottleneck / KeyDataPoint

Step 4. Convergence check
   - Did this round introduce new Companies?
   - Is each L3 sub-theme connected to at least N companies?
   - Are there Bottlenecks for each Company at the critical-layer level?
   If yes → continue; if no → declare converged.

Step 5. Generate cross-theme synthesis
   Tier 1 agent task: "Across all sub-themes under this theme, which hub
   suppliers appear in ≥3 anchors? Add InvestmentThesis entities for
   each."
   → adds InvestmentThesis + watched_in relations
```

### 3.3 Components to build

```
[Theme decomposer]
└── theme_to_subthemes(theme_id) → [SubTheme | Technology | Sector]
        Uses LLM + existing taxonomy in shared/themes.json

[Cascade orchestrator]
├── queue: list[Task]
├── scheduler: round-robin across L3 sub-themes
├── dedupe: skip Companies already covered
└── budget tracker: max_total_turns, max_total_entities

[Coverage evaluator]
├── per L3: are there ≥ N companies covered? (N from policy)
├── per Company: at least 1 Bottleneck + 3 KeyDataPoints?
└── threshold: 0.9 coverage → declare done

[Bookkeeping]
└── Each cascade run records:
      - input theme
      - sub-themes discovered
      - companies added (this run vs preexisting)
      - bottlenecks/KDPs added
      - convergence flag + reason
```

### 3.4 Relationship to shinkai Mode B

This **is** Mode B at the data layer: theme → frontier expansion → candidate
companies → dossiers. The existing ``ShinkaiHarness`` already implements much
of the orchestration loop. Tier 3 is mostly "rewire Mode B's writes to go
through the industry_graph tools instead of (or in addition to) the
research/graph stores", with the cascade evaluator added at the end.

This means the Tier 3 build is **much less new code than it looks**:
- Reuse ``agent/harness.py`` for the frontier/queue mechanics.
- Reuse ``agent/frontier.py`` for layer expansion.
- Replace direct ``default_research_store`` writes with
  ``IndustryGraphStore`` ``upsert_entity`` / ``upsert_relation`` /
  ``add_bottleneck`` calls (via the dispatcher).
- Add the coverage evaluator on top.

### 3.5 Open questions

- Coverage thresholds: per-theme tunable, or globally fixed?
- Theme decomposition: cache decompositions in ``shared/themes.json`` so we
  don't re-ask the LLM on every cascade run?
- Cross-cascade dedup: two themes touch overlapping companies (AI Infra and
  Power both touch Vertiv). The first cascade "owns" the company; how do
  later cascades enrich without churning the snapshot history?

---

## 4. Investment Structure (deferred, but spec'd here)

Two new facet-axis facts to capture in V0.5 (no agent-tier change required;
schema additions only):

### 4.1 New relation types

| Type | Direction | Semantics |
|---|---|---|
| ``invested_by`` | ``Fund/VC → Company`` | Holdings (13F, S-1 cap table) |
| ``shareholder_of`` | ``Company → Company`` | Cross-holdings (Toyota → Tesla, etc.) |
| ``subsidiary_of`` | ``Company → Company`` | Parent / sub relationships |
| ``acquired`` | ``Company → Company`` | Closed acquisitions (with date in attributes) |

Each carries weights (``stake_pct``, ``shares_held``, ``vintage``) and
provenance.

### 4.2 New entity kinds

- ``Fund`` — institutional holders, VC firms, sovereign wealth funds.
- ``Person`` — material insiders (CEO, founder), for cap-table modelling.

### 4.3 Data sources

| Source | Cadence | Tool to add |
|---|---|---|
| SEC 13F filings | Quarterly | ``sec_13f_fetch(fund_id, quarter)`` |
| SEC S-1 / S-3 cap tables | Per filing | ``sec_capital_table(ticker)`` |
| Crunchbase | On demand | ``crunchbase_funding(company)`` |
| Company press releases | Continuous | News feed scanner |

### 4.4 Why it's small

The schema additions are exactly the kind of forward-compatible move the V0
spec was designed for. No migration; just append to the ``RelationType``
literal and add new tools. Agent code (Tier 1 / 2 / 3) needs no changes.

---

## 5. Priority

| Rank | Item | Cost | Unblocks |
|---|---|---|---|
| **P0** | Tier 1.5 polish (loop-detection, source auto-register, schema re-validation in tools, done-prompt) | S | Reliable single-session results, prevents demo-quality regressions |
| **P1** | Tier 3 cascade *by wiring Mode B to industry_graph tools* (much smaller than building from scratch) | M | Real "give me a theme, get a saturated subgraph" UX |
| **P2** | Tier 2 proactive scanners + orchestrator | M-L | Continuous coverage, less user prompting |
| **P3** | Investment structure (schema + ingestion) | S | New analytical lens, completes the multi-facet model |
| **P4** | Multi-agent collaboration (supervisor + workers) | L | Complex composite tasks (review, falsification, synthesis) |

---

## 6. Acceptance criteria per tier

A tier is "done" when:

### Tier 1.5
- ``E2E #1``-style repeated-query failures no longer occur.
- Every write tool gracefully validates input and returns structured errors.
- Sessions reliably emit ``done`` when work is complete.

### Tier 2
- A cron-style trigger runs daily and adds at least one new Company to the
  graph that wasn't there yesterday.
- The orchestrator handles a 10-entity gap list without runaway spawning.
- The audit log records both the policy that triggered each session and the
  outputs.

### Tier 3
- Giving the agent ``"AI Infrastructure"`` produces ≥ 30 Company entities, ≥
  10 Bottleneck entities, and ≥ 50 KeyDataPoints in one session.
- The coverage evaluator declares convergence, not "max budget hit".
- Running the same theme a week later **does not** materially churn the
  snapshot history (dedup works).

---

## 7. What is *not* in this document

- The web-side cockpit / UI flows that consume the graph (covered by the
  existing demo and forthcoming dashboard work).
- The Mode A value-investing checklist (already specced in
  ``docs/checklists/value-investing-v1.md``).
- Detailed token-budget / cost modelling — needs a separate ops note once
  Tier 2 is running.
- Multi-LLM routing (DeepSeek vs Claude vs others) — orthogonal; the
  ``LLMRouter`` decision lives in ``docs/alignment-v2.md``.

---

**End of V0 spec.** Review and revise before starting Tier 2/3 work.
