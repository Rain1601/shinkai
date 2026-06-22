# Shinkai Changelog

A trace of milestones, integrations, and updates to shinkai — the
long-running, observable investment-research agent for US equities.

Newest first. Each entry is tagged:

- **`milestone`** — direction-shifting or load-bearing additions we will
  reference in future decisions
- **`integration`** — new external data source or downstream consumer
- **`feature`** — net-new capability that is not a milestone on its own
- **`ui`** / **`design`** — surface-level rework that meaningfully
  changes how the product is used or perceived
- **`fix`** — bug repair
- **`docs`** — written knowledge updates
- **`decision`** — a choice we made and want future selves to find

Commit hashes link back to git. To extend the changelog: add a new
entry at the top under the current month, prefer the tightest type
that fits.

---

## 2026-06-22

### [ui] Overview KPI tighten

Status card keeps full-width hero treatment; Subjects / Versions / Store
collapse into a single 3-up row. Eyebrows shed verbosity ("STATUS ·
Subjects · tracked · Versions · lifetime · Store · coverage" → single
words). AgentIdentityStrip removed from overview/agent/history shells
since the hero already shows identity.

- `da7ee27` ui(web): tighten Overview KPIs — status hero + 3-up row

---

## 2026-06-21 → 06-22 · Run-centric reframe

### [milestone] /agent becomes the home screen

The `/industry-graph` workspace is promoted to the agent's home; the
unit of work is now **Subject + SubjectVersion**, not "run id". `/runs`
is rewritten as a SubjectVersion log, `/actions` retired, and
PortalShell nav flattened around the new IA.

- `f2e4ee1` feat(web): promote Overview to its own /overview route
- `f0b2905` feat(web): Stage 7 — SubjectVersion detail at /runs/sv:<id>
- `1ba7742` feat(web): Stage 6 — rewrite /runs as agent SubjectVersion log
- `767c528` feat(web): Stage 5 — AgentIdentityStrip + flat PortalShell nav
- `837a69d` feat(web): Stage 4 — Overview tab inside /agent
- `1bd8957` refactor(web): Stages 2+3 — promote /industry-graph → /agent
- `cad8b31` feat(industry_graph): Stage 1 — GET /runs + GET /runs/{sv_id}
- `d610b23` ui(web): move Industry Graph into the Workspace nav section
- `a8a1fa4` feat(web): rebuild /agent as a Subject-centric overview dashboard
- `b5309f0` refactor(web): retire /actions, redirect to /industry-graph

---

## 2026-06-21 · Industry Graph V0 → live + interactive

### [milestone] Industry Graph V0 ships

10 entity kinds, 13 relation types, ~26 graph tools, multi-turn agent
loop that drives them. The graph is live-exported and visualised in a
Cytoscape preview pane. Stage 1-7 then layers Subject + SubjectVersion
domain on top, so every run produces a versioned anchor-focused
subgraph rather than a flat blob.

- `2dd5efd` docs: industry-graph V0 schema spec (10 entity kinds, 13 relations, 25+ tools)
- `f049367` feat(api): industry_graph V0 — schemas, file store, 26 tools, ingestion
- `b07d6c7` feat(api): multi-turn agent loop driving industry_graph tools
- `279d9d7` docs: agent tier-progression V0 (Tier 1 implemented, 2/3 planned)
- `801b14e` feat: Tier 1.5 polish — repeat detection, auto source, schema re-validate
- `813aa47` feat: live export endpoint + cytoscape preview page
- `e4e1c05` feat(web): expose Industry Graph in portal sidebar
- `8f5031b` fix(web): restyle live industry graph to match manganese palette
- `c8f95f5` fix: redesign live view as anchor-focused subgraph
- `db2d0a0` feat: derive supply-chain strata + sub-arrange suppliers
- `f924973` feat: canonicalize supply_layer on every write
- `07920b5` feat(web): morph animation on anchor switch
- `29551b4` feat: Stage 1 — Subject + SubjectVersion domain layer
- `6e77f6e` feat: Stage 2 — migration backfill for Subjects
- `1589696` feat: Stage 3 — orchestrator + POST /subjects/{id}/run
- `66d0e89` feat: Stage 4 — version detail + reconstructed-graph endpoints
- `00b82ab` feat: Stage 5 — Subject event feed
- `ef7725f` feat(web): Stage 6 — Industry Graph list page at /industry-graph
- `5d58fa4` feat(web): Stage 7 — Subject detail page at /industry-graph/[subjectId]
- `29c8f91` chore(web): add cytoscape@3 + @types/cytoscape + Stage 7 CSS
- `a1dcf31` fix(web): scope the analyses rail to the selected subject
- `b58b300` feat(web): bring the detail page within sight of the NVIDIA-atlas demo

### [feature] Theme + cross-subject merge

Second wave (Stage 1-7 of a `/live` merge): themes are first-class
subjects, the graph shows what's "affected by" what, and the list page
gets an Activity tab.

- `4cb1b36` feat: Stage 1 of /live merge — affected_by + /activity
- `f6610f0` feat: Stage 2 — /subjects/{id}/members for Theme subjects
- `e4a29fd` feat(web): Stage 3 — Theme detail specialized view
- `e86412f` feat(web): Stage 4 — Activity tab on /industry-graph list page
- `c958989` feat(web): Stages 5+6 — Detail Activity section + 参与主题 chip
- `277c450` feat(web): Stage 7 — /live → /industry-graph redirect, nav cleanup

### [feature] Graph interactions

- `33adfd0` feat(web): graph interactions — node hover, edge tooltip, drag-Y, strata hover
- `9e4c69d` feat(web): Edge click swaps right pane to EdgePane
- `51bbf3a` feat(web): dbltap node → navigate to that Subject's detail page
- `2d39c91` ui(web): give the graph the dominant share of the detail viewport
- `dd169ff` feat(web): focus breadcrumb above the graph
- `56c7b94` fix(web): edge click highlights selected edge + endpoints

---

## 2026-06-21 · fxbaogao Phase 1 integration

### [integration] 发现报告 corpus via MCP HTTP

shinkai gains direct access to 3M+ Chinese sell-side research reports
through fxbaogao's MCP endpoint. Three tools (`fxbg_search` /
`fxbg_paragraphs` / `fxbg_pdf_url`); the first two are free, the third
consumes 1 of 300 monthly PDF downloads. Phase 1 is **manual** — the
harness does not auto-call yet, exploration goes through
`scripts/fxbg_explore.py`.

Defaults to MS / GS / Nomura issuer whitelist + drops `未知机构` and
sub-3-page rumor blasts. Empirically: same query without the filter
returned 40% noise; with it, 100% of top-10 hits are actionable.

- `43d0cc2` feat(tools): add fxbaogao MCP HTTP client (phase 1 — manual use only)
- `c88293d` feat(tools): default fxbg_search to MS/GS/Nomura whitelist + noise filter

---

## 2026-06-20 · Manganese Floor design adoption

### [milestone] Switch app palette from cold abyss to warm sediment

Replaces the prior **Pearl & Weight** dark-blue palette (Jun 2) with
**Manganese Floor** — warm-charcoal canvas + oxidized teal accent +
copper highlight. Picked after comparing 4 candidates side-by-side on
real product fragments (`/palettes-gallery.html`). The 5 supporting
secondaries (sulfur / cold coral / cephalopod / phosphor / hematite)
are documented but not yet adopted.

Sidebar simultaneously ported from a flat 5-item mono-caps list to
the uteki pattern: section labels (Workspace / Engine / Knowledge),
Fraunces italic display labels, accent-fill active state with left bar.

- `b7c5c62` design(web): switch app palette to Manganese Floor (warm sediment)
- `5ac02ca` design(web): add deep-sea palette specimen gallery (4 candidates × day/night)
- `2319f68` design(web): port uteki sidebar pattern — sections, display labels, active fill+bar
- `1ac6a7d` design(web): add supporting-palette ecosystem section to gallery (5 secondaries)
- `32660d3` fix(web): collapse portal sidebar after click by switching :focus-within to :has(:focus-visible)
- `72cd662` feat(web): add industry graph mock — drill-down nav + supply-chain rail
- `a0f7951` docs: refresh web_search backend section to market-utils SearchEngine

---

## 2026-06-18 · Premium publisher search

### [milestone] Agent Search + source-quality bias

Adds Vertex AI Discovery Engine's Standard tier (`searchLite`) as a
premium-publisher strategy for Mode A deep research, and biases the
default Vertex Grounding away from aggregators toward primary +
trade-press sources.

- `743e450` feat(search): wire Agent Search premium-publisher strategy + provisioning script
- `7448f3b` feat(search): switch agent_search consumer to engine + searchLite (Standard tier works)
- `1d643e7` fix(scripts): pass x-goog-user-project header so user ADC works
- `25ec039` feat(research): aggregator-aware reliability score + wire through harness
- `c01d83f` feat(harness): web_extract prefers first non-aggregator result
- `ae5ae49` feat(harness): bias Vertex Grounding toward primary + trade-press sources
- `a43cf8f` feat(search): push NOISE_DOMAINS to Vertex exclude_domains via bridge
- `cbaad81` docs: correct vertex-search-scope-control with 2026-06 capability updates

---

## 2026-06-17 · Vertex Grounding replaces CSE

### [milestone] Web search backend switched to Vertex AI Grounding

Google closed Custom Search JSON API to new GCP customers in 2025.
shinkai (and the cross-project `market-utils` package it shares with
uteki) switches to Vertex AI Gemini + `google_search` tool, two-pass
(ground → structure into SearchResult rows). End-to-end verified;
returns real publisher URLs (Bloomberg, TrendForce, etc.) not proxy
redirects. ~$0.04 / search.

- `e99496d` feat(search): switch web search to Vertex AI Grounding
- `2b72224` docs: add Vertex AI search scope control reference
- `2cab02a` fix(research): widen classify_source_tier to catch corporate newsrooms and more publishers
- `7544ec1` chore(tests): wrap long source-tier test URLs to satisfy ruff E501
- `6295520` feat(search): noise-source blocklist + exact-URL dedup for web_search
- `a6525dd` feat(search): retry Vertex 429 once, then fall back through the chain

---

## 2026-06-16 · Theme-centric workspace

### [milestone] Themes become first-class engine objects

Web search routed through the in-house `market-utils` package; UI
acquires a theme-centric workspace + theme graph + ThemeEvent
ingestion. Sets up the eventual Industry Graph V0 (Jun 21).

- `03df96b` refactor(api): route web search through market-utils package
- `9aa3e1a` feat: theme-centric workspace + theme graph + ThemeEvent ingestion

---

## 2026-06-03 · Theme system + viewport polish

### [feature] Day/night theme toggle + semantic CSS vars

- `4ae96ef` feat(web): day/night theme toggle + theme-independent typography
- `49e0093` refactor(web): swap hard-coded hex for semantic CSS vars in portal panels
- `7fc9caa` fix(web): sidebar logo subtitle overflowing the narrow rail
- `d0a4acd` fix(web): /agent fits one viewport — Active Work scrolls internally
- `1e66413` fix(web): /actions fits one viewport — each panel scrolls internally
- `a3747ba` polish(web): tighten sidebar hover-expand timing
- `29de66a` polish(web): bump sidebar timing to 240/180ms — middle ground
- `ef44c27` style(web): pull canvas back from twilight indigo to deep cool black
- `05ece1d` style(web): lift canvas one notch — slightly more blue undertone

---

## 2026-06-02 · Real evidence layer + brand identity

### [milestone] Agent talks to the real web

First time the harness exits stub-land: Tavily search + ticker
validator (yfinance + SEC EDGAR fallback) + direct SEC filings tool.
The hard industry blacklist (Healthcare / Real Estate / Financial
Services / Utilities / Lodging / Casinos) catches LLM hallucinations
like "ATYR Pharma for HBM" before they pollute the dossier.

- `a69b033` feat(agent): real evidence layer — Tavily search + ticker validator + SEC EDGAR

### [design] Brand identity v1: depth-sounder mark + Pearl palette

Replaces the placeholder compass with a depth-sounder mark (inverted
triangle + descending dots — nautical chart for descent). Palette L ·
Pearl & Weight: near-black canvas + neutral pearl text + single muted
steel-blue accent. (Pearl was replaced by Manganese on Jun 20.)

- `25da963` feat(web): shinkai depth-sounder mark replaces compass logo
- `ad7af73` style(web): swap to palette L · Pearl & Weight
- `8006af4` style(web): lift canvas to twilight indigo
- `c547c52` feat(auth): backend JWT session verification + NextAuth scaffold

---

## 2026-06-01 · Path-A/B convergence + cockpit IA

### [milestone] Inject-checkpoint loop closes

Path A (hypothesis state machine + LLM-driven frontier + L2 critic
personas) and Path B (human-in-the-loop injection checkpoint) converge.
The cockpit IA is refactored across 5 sub-stages (P1-P5) into the
Agent / Live / Actions / History shape that holds until the Jun 21
industry-graph rework.

- `c91dbde` feat(agent,web): close inject-checkpoint thinking loop (path B+)
- `e6c6ee2` feat(agent): hypothesis state machine + injection effects (path A G1+G2)
- `7492e6d` feat(web): cockpit IA refactor (path A G3-G5)
- `2cc254a` feat(agent): LLM actually drives frontier, with fail-fast + validation
- `b9251e9` feat(agent): wire L2 critic personas into the harness
- `9a4b947` feat(web): time anchor + recap card for return visits (P2)
- `894b753` feat(agent,web): reasoning trail / framework tab (P1)
- `2010f53` feat(agent,web): theme aggregation pages (P3)
- `059420b` feat(agent,web): IA refactor — Agent overview page (P1)
- `367122f` feat(agent,web): actions inbox + capability matrix (P2)
- `1bdf288` feat(agent,web): live cockpit + history view toggle + docs (P3+P4+P5)
- `e1d687d` refactor(web): flatten /live cockpit — hairlines, no nested boxes

---

## 2026-05-31 · Day 0 — bootstrap

### [milestone] Observable agent runtime + bilingual dashboard ship

Day 0 of shinkai. Scaffolds the monorepo, the observable agent
runtime, the bilingual ops dashboard, CI + Cloud Run deployment, the
evidence domain models, the research state store, the
evidence-backed research loop, the frontier queue planner, company
dossiers, and the eval scaffold with golden adversarial cases.

- `5f504de` chore: scaffold shinkai workspace
- `cd8b9c6` docs: add shinkai agent specifications
- `77f0672` feat(api): implement observable agent runtime
- `54a4101` feat(web): implement bilingual operations dashboard
- `ef8dcde` ci: add verification and cloud run deployment
- `263d828` feat(auth): formalize read access roles
- `0b638ed` test: stabilize run executor waits
- `cfb17f0` fix(web): improve runs page interactions
- `fc4c065` feat(research): add evidence domain models
- `b0c3d0e` feat(persistence): add research state store
- `0996b12` feat(agent): persist evidence-backed research loop
- `ec3b54d` feat(research): harden evidence trust review
- `9255a24` feat(agent): add frontier queue planning
- `be9fcce` feat(research): add company dossiers
- `36944bf` feat(runtime): recover and guard agent runs
- `d4954f0` feat(eval): score claim and dossier quality
- `3c54333` test(eval): add golden adversarial cases
- `b544155` feat(results): add published research snapshots
- `5d23297` feat(persistence): project postgres state tables
- `ad99029` fix(agent,runtime,persistence,eval): close review findings end-to-end
- `e5e8f4f` docs: add CLAUDE.md and alignment-v2 implementation status map
