# Industry Graph Schema V0

> Single source of truth for shinkai's industry graph — the machine-readable side of the
> dual output. Designed for agent-driven ingestion and LLM-friendly editing.

**Status**: V0 design, pre-implementation. Audit and refine before writing code.

**Relation to other docs**:
- `research-graph-schema-v0.md` defines the *reasoning* graph (Claim / Evidence / Question / Thesis).
- This document defines the *industry* graph (Company / Product / Bottleneck / supply chain).
- They share the `Source` / `Provenance` model and the snapshot/version mechanism.
- Industry graph is the substrate; research graph reasons *about* it.

---

## 0. Goals & Non-Goals

**Goals**
- Capture multi-facet industry knowledge (concept hierarchy + value chain + sector + region) in one extensible model.
- Be **agent-editable** — Claude Code / Codex / future autonomous agents can `cat` / `sed` / `Edit` JSON files directly. Diffs reviewable in git.
- Make **bottleneck / key metric / investment thesis** first-class — these are shinkai's alpha.
- Idempotent + versioned writes — every fact has provenance, every change is auditable.

**Non-Goals (V0)**
- Multi-user concurrent writes (V1+).
- Real-time graph algorithms over 100K+ nodes (V2+).
- Public-facing API (internal agent tools only).

---

## 1. Design Principles

1. **Open-world / multi-facet** — an entity can simultaneously be a Company, sit in `Sector=Semiconductor`, `Region=TW`, `chain_layer=foundry`, themed under both `AI Infrastructure` and `Physical AI`. Facets are independent axes.
2. **Provenance everywhere** — every entity, relation, attribute, and weight carries `[Provenance]` (source + page + quote + confidence + evidence_type). No fact lives unattributed.
3. **First-class analysis nodes** — `Bottleneck` / `KeyDataPoint` / `InvestmentThesis` are entities (can have multiple sources, affect multiple targets, evolve over time), not attributes on Company.
4. **Open-ended attributes** — every kind has a `attributes: dict[str, Any]` field. New domain-specific properties go there. Schema additions don't break existing data.
5. **Idempotent + versioned** — `upsert_*` operations dedupe by stable ID. Every write commits to an append-only audit log. Snapshots use incremental diff against a parent.
6. **Agent-friendly storage** — JSON files on disk, target-sharded, human-readable. Pydantic validates on read/write. In-memory indices serve queries.

---

## 2. Entity Types

10 kinds, grouped by role.

### 2.1 Concept Hierarchy (L1–L6+, dynamic depth)

| kind | level | examples |
|---|---|---|
| `Theme` | L1 | AI · Energy Transition · Aging Population · Defense Tech |
| `SubTheme` | L2 | AI Infrastructure · AI Models · Physical AI · AI Applications · AI Economic Impact |
| `Technology` | L3 | GPU · ASIC · HBM · CoWoS · CPO · GaN · Harmonic Drive · VLA Model |
| `Company` | L4 | NVDA · TSMC · 绿的谐波 · Optimus suppliers |
| `Product` | L5 | B300 · Rubin R200 · Optimus Gen3 · DGX SuperPod |
| `Component` | L6+ | SoC Die · HBM Stack · CoWoS Interposer · Servo Encoder (can nest further) |

Depth is **dynamic**. NVDA → B300 → SoC Die → SM Core is 6 levels; 绿的谐波 → LHS series → LHS-25-50A is 7. The `concept_level` field is informational, not structural — hierarchy comes from `contains` / `is_a` / `part_of` edges.

### 2.2 Horizontal Facet Entities

| kind | purpose |
|---|---|
| `Sector` | Industry classification (Semiconductor / Data Center / Power Grid / Robotics / EV). |
| `Region` | Geography (US / TW / KR / CN / JP / EU / SG). |
| `SupplyLayer` | Value-chain position (designer / foundry / packaging / memory / testing / assembly / cooling / power / networking). |
| `TimeHorizon` | Catalyst horizon (short < 3M / medium 1-2Y / long > 3Y). |

These exist as entities so they can be referenced, listed, and counted. Companies attach via edges (`belongs_to_sector` / `headquartered_in` / etc.).

### 2.3 Analysis Entities (shinkai's alpha)

| kind | purpose |
|---|---|
| `Bottleneck` | A capacity / geopolitical / technology / demand / regulation constraint. Carries `type`, `severity`, `status`, `affects:[Company]`, sources. |
| `KeyDataPoint` | A quantitative fact: `metric`, `value`, `period`, `unit`, `subject`, source. Examples: "NVDA CoWoS 2026e = 875k wafers". |
| `InvestmentThesis` | A research-derived investment view: `target_company`, `stocks_to_watch:[{ticker, rationale, pt?}]`, `bias`, source. |

### 2.4 Source

| kind | purpose |
|---|---|
| `Source` | A research report or original publication. Carries `publisher`, `title`, `date`, `url`, `pages_relevant`, `hash`. |

---

## 3. Entity Base Schema (Pydantic)

```python
from typing import Annotated, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

EntityKind = Literal[
    "Theme", "SubTheme", "Technology", "Company", "Product", "Component",
    "Sector", "Region", "SupplyLayer", "TimeHorizon",
    "Bottleneck", "KeyDataPoint", "InvestmentThesis",
    "Source",
]

class FacetSet(BaseModel):
    """Multi-axis classification. All optional. Any new facet is just a new field
    or goes into `extras` dict — no schema migration needed."""
    model_config = ConfigDict(extra="allow")

    concept_level: int | None = None       # 1-6+
    sectors: list[str] = []
    regions: list[str] = []
    chain_layers: list[str] = []
    time_horizons: list[str] = []
    # Extensible: future axes added without breaking existing data.

class ProvenanceRef(BaseModel):
    source_id: str                         # references a Source entity
    page: int | None = None
    quote: str | None = None
    confidence: float = 1.0                # 0-1
    evidence_type: Literal["hard_data", "soft_inference"] = "hard_data"
    asserted_at: datetime
    asserted_by: str | None = None         # run_id / agent_id

class EntityBase(BaseModel):
    id: str                                # stable URI: co:NVDA / bn:nvda_cowos_2026
    kind: EntityKind
    labels: list[str]                      # ["NVIDIA Corporation", "英伟达"]
    aliases: list[str] = []                # ["NVDA", "Nvidia", "NVDA.US"]
    description: str | None = None
    facets: FacetSet = Field(default_factory=FacetSet)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = []
    confidence: float = 1.0
    snapshot_version: int = 0
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

**Kind-specific attributes (examples)**:

```python
# Company
attributes = {
    "ticker": "NVDA",
    "exchange": "NASDAQ",
    "market_cap_usd_bn": 3500,
    "ipo_year": 1999,
    "country_hq": "US",
}

# Bottleneck
attributes = {
    "type": "capacity",                    # capacity / geopolitical / technology / demand / regulation
    "severity": "high",                    # high / medium / low
    "status": "active",                    # active / resolved / monitoring
    "expected_resolution": "2H27",
    "affected_layer": "advanced_packaging",
}

# KeyDataPoint
attributes = {
    "metric": "CoWoS wafer allocation",
    "value": "875k",
    "value_numeric": 875000,
    "unit": "wafers",
    "period": "2026e",
    "subject_id": "co:NVDA",
}

# InvestmentThesis
attributes = {
    "target_id": "co:NVDA",
    "stocks_to_watch": [
        {"ticker": "2330.TW", "rationale": "Necessary CoWoS exposure", "pt": "NT$2588"},
        {"ticker": "000660.KS", "rationale": "HBM primary"},
    ],
    "bias": "constructive",                # bullish / constructive / cautious / bearish
    "horizon": "medium",
}

# Source
attributes = {
    "publisher": "MS",
    "title": "Build for future AI infrastructure",
    "date": "2026-05-08",
    "url": "...",
    "pages_relevant": [3, 13, 18, 29],
    "hash": "sha256:...",
    "asset_class": "equity",
    "region_focus": "global",
}
```

Schema growth = add keys to `attributes`. Existing data stays valid.

---

## 4. Relation Types

13 types, grouped by purpose.

### 4.1 Hierarchy (concept tree)

| type | semantic | direction |
|---|---|---|
| `contains` | parent contains child | L1 → L2 → L3 → ... |
| `is_a` | product belongs to company | Product → Company |
| `part_of` | component is part of product | Component → Product |
| `variant_of` | variant of base product | Variant → BaseProduct |

### 4.2 Multi-Facet Tagging (many-to-many)

| type | semantic |
|---|---|
| `themed_under` | Company → SubTheme (NVDA themed under AI Infra + Physical AI + AI Models) |
| `uses_tech` | Company → Technology |
| `belongs_to_sector` | Company → Sector |
| `headquartered_in` | Company → Region |

### 4.3 Value Chain (industry topology)

| type | semantic |
|---|---|
| `supplies_to` | Company → Company (carries weights: buyer_spend / seller_rev / lock_in) |
| `competes_with` | Company ↔ Company (carries `relationship: alternative/substitute`, `threat_level`, `share_delta`) |
| `produces` | Company → Product |

### 4.4 Analysis Linkage

| type | semantic |
|---|---|
| `bottleneck_at` | Bottleneck → SupplyLayer / Bottleneck → Company |
| `affects` | Bottleneck → Company[] (which anchors are impacted) |
| `key_data_about` | KeyDataPoint → Entity (subject of the metric) |
| `watched_in` | InvestmentThesis → Company (stocks_to_watch member) |

---

## 5. Relation Base Schema (Pydantic)

```python
RelationType = Literal[
    "contains", "is_a", "part_of", "variant_of",
    "themed_under", "uses_tech", "belongs_to_sector", "headquartered_in",
    "supplies_to", "competes_with", "produces",
    "bottleneck_at", "affects", "key_data_about", "watched_in",
]

class WeightCell(BaseModel):
    """A single time-period weight observation."""
    model_config = ConfigDict(extra="allow")

    period: str                            # "2026" / "2026Q1" / "2026e" / "2024..2027"
    values: dict[str, float]               # core named fields (typed) + extras

class RelationBase(BaseModel):
    id: str                                # ULID or domain-sortable
    type: RelationType
    source_id: str                         # entity id
    target_id: str                         # entity id
    weights: list[WeightCell] = []         # time series; empty for non-quantitative edges
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = []
    confidence: float = 1.0
    snapshot_version: int = 0
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

**Weight schemas per relation type** (named keys in `WeightCell.values`):

```python
# supplies_to:
{"buyer_spend": 0.78, "seller_revenue": 0.21, "lock_in": 0.95}

# competes_with:
{"direct_overlap": 0.85, "share_delta": -0.02}
# attributes:
#   {"relationship": "alternative" | "substitute", "threat_level": "high|medium|low"}

# bottleneck_at:
{"severity_score": 0.9}
# attributes from parent Bottleneck entity, mirrored where useful
```

New weight dimensions = new keys in `values`. No schema migration.

---

## 6. Stable ID Convention

```
Themes:       th:AI
SubThemes:    st:ai_infrastructure
Technologies: tech:hbm
Sectors:      sec:semiconductor
Regions:      reg:TW
SupplyLayers: lay:foundry
Companies:    co:NVDA       (ticker preferred when available)
              co:绿的谐波  (slug for non-listed)
Products:     pd:nvda_b300
Components:   cmp:nvda_b300_soc_die
Bottlenecks:  bn:cowos_capacity_2026
KeyData:      kdp:nvda_cowos_alloc_2026
Theses:       th:ms_nvda_20260508
Sources:      src:ms_20260508_ai_infra
Relations:    r:co:nvda~supplies_to~co:microsoft~2026
                or ULID for uniqueness
```

ID = `{prefix}:{slug}`. Prefix is the kind, slug is human-readable. Stable across snapshots.

---

## 7. File Layout

```
.shinkai/industry_graph/
├── manifest.json                  # current_snapshot_version + index of targets
├── current/
│   ├── targets/
│   │   ├── NVDA.json              # full atlas: NVDA's entities + relations + bottlenecks + KDPs + theses
│   │   ├── AAPL.json
│   │   ├── HBM.json               # theme target
│   │   ├── ROBOTICS.json
│   │   └── ...
│   ├── shared/
│   │   ├── companies.json         # cross-target entities (TSMC supplies many anchors — stored once here)
│   │   ├── themes.json            # L1 / L2 / L3 concept tree
│   │   ├── technologies.json
│   │   ├── sectors.json
│   │   ├── regions.json
│   │   ├── supply_layers.json
│   │   └── sources.json           # all research reports
│   └── meta.json                  # current snapshot metadata
├── snapshots/
│   ├── v0001/
│   │   ├── meta.json              # {parent: null, created_at, run_id, rationale, changeset_summary}
│   │   └── changes.jsonl          # incremental diff against parent (op / entity_or_relation / id / before / after)
│   ├── v0002/
│   │   └── ...
│   └── ...
├── indices/                       # derived, regenerable; checked into git or not (TBD)
│   └── fulltext.db                # Whoosh index for description / quote search
└── audit.jsonl                    # append-only log of all writes (op / actor / time / changes)
```

### 7.1 Sharding Rules

- **Target shards** (`targets/NVDA.json`) hold:
  - `Bottleneck` / `KeyDataPoint` / `InvestmentThesis` *specific to that anchor*
  - Relations *anchored on this target* (e.g., the `supplies_to` edges pointing into NVDA)
  - Local provenance refs

- **Shared shards** (`shared/companies.json`, etc.) hold:
  - `Company` / `Product` / `Component` entities that are reused across multiple targets
  - `Theme` / `SubTheme` / `Technology` / `Sector` / `Region` / `SupplyLayer` taxonomies
  - `Source` registry

- **Cross-shard references** use stable IDs. A NVDA-shard relation referencing TSMC reads `target_id: "co:TSMC"` and resolves against `shared/companies.json`.

### 7.2 Concurrency

- One writer at a time (V0 is single-user).
- File lock via `fcntl.flock(fd, LOCK_EX)` on `manifest.json`.
- Reads non-blocking (use `LOCK_SH` if needed).
- All writes wrap: acquire lock → load → mutate → validate → write → append audit → release.

---

## 8. Snapshot / Versioning (Incremental Diff)

Each snapshot is a small file containing the diff against its parent, **not a full copy**.

```python
# snapshots/v0002/meta.json
{
  "version": 2,
  "parent_version": 1,
  "created_at": "2026-06-21T15:32:00Z",
  "created_by_run_id": "run_abc123",
  "rationale": "Ingested MS 20260508 — NVDA AI infrastructure atlas",
  "changeset_summary": {
    "entities_added": 17,
    "entities_updated": 3,
    "relations_added": 42,
    "relations_updated": 5,
    "bottlenecks_added": 8,
    "key_data_added": 18,
  }
}

# snapshots/v0002/changes.jsonl  (one JSON per line)
{"op": "insert", "kind": "entity", "id": "co:NVDA", "after": {...}}
{"op": "update", "kind": "entity", "id": "co:TSMC", "before": {...}, "after": {...}}
{"op": "insert", "kind": "relation", "id": "r:...", "after": {...}}
{"op": "insert", "kind": "entity", "id": "bn:cowos_2026", "after": {...}}
{"op": "deprecate", "kind": "relation", "id": "r:...", "before": {...}}
...
```

### 8.1 Reconstruction

`current/` is always the latest fully-resolved state. To reconstruct an older version, apply diffs from snapshot v=N back to v=1 in reverse.

Alternatively, build a cache: every Nth snapshot (e.g., every 50) writes a full copy alongside diff, to bound reconstruction time.

### 8.2 Branching / Forking (V1+)

V0: linear snapshot chain.
V1+: snapshot DAG (`parent_version` becomes a list to support merges, or branches via `branch_name`).

---

## 9. In-Memory Index Layer

On startup, the file store loads all shards into memory and builds:

```python
class IndexLayer:
    by_id: dict[str, Entity | Relation]
    by_kind: dict[EntityKind, list[Entity]]
    by_facet: dict[tuple[str, str], list[Entity]]       # (facet_name, value) -> entities
    by_ticker: dict[str, Entity]
    relations_by_source: dict[str, list[Relation]]
    relations_by_target: dict[str, list[Relation]]
    relations_by_type: dict[RelationType, list[Relation]]
    graph: nx.MultiDiGraph                              # NetworkX, full graph
    fulltext: WhooshSearcher                            # description / quote
```

**Reindex** on every write (incremental — only touched ids). Full reindex on snapshot revert.

**Memory footprint** (forecast):
- 20K entities × ~1KB = 20MB
- 100K relations × ~0.5KB = 50MB
- NetworkX overhead × 2 ≈ 140MB
- Whoosh index ≈ 50-100MB on disk, smaller in cache

Total comfortably < 500MB even at V2 scale.

---

## 10. Function Tools (Agent-Callable)

~25 tools, grouped. Every write tool requires `source_ref: ProvenanceRef`.

### 10.1 Query (no provenance required)

```python
def find_entity(
    *, query: str | None = None,
    kind: EntityKind | None = None,
    facets: dict[str, str] | None = None,
    limit: int = 20,
) -> list[Entity]:
    """Search entities by name / alias / description / facets."""

def get_entity(id: str) -> Entity | None:
    """Get full entity with relations."""

def find_relations(
    *, source: str | None = None, target: str | None = None,
    type: RelationType | None = None, period: str | None = None,
) -> list[Relation]:
    """Filter relations."""

def walk_path(from_id: str, to_id: str, *, max_depth: int = 4,
              edge_types: list[RelationType] | None = None) -> list[list[str]]:
    """Find paths between two entities."""

def find_bottlenecks(*, anchor_id: str | None = None,
                     type: str | None = None,
                     severity_min: Literal["low", "medium", "high"] = "medium"
                     ) -> list[Entity]:
    """Find bottlenecks affecting an anchor."""

def find_key_data(subject_id: str, *, metric_substr: str | None = None,
                  period: str | None = None) -> list[Entity]:
    """Get quantitative facts about a subject."""

def search_sources(*, publisher: str | None = None,
                   ticker: str | None = None,
                   date_from: str | None = None,
                   date_to: str | None = None) -> list[Entity]:
    """Find research reports matching criteria."""

def list_facet_values(facet_name: str) -> list[str]:
    """Enumerate values seen in this facet (for UI dropdowns / agent context)."""

def fulltext_search(query: str, *, limit: int = 20) -> list[Entity]:
    """Full-text search across description / quote fields."""
```

### 10.2 Entity Write

```python
def register_source(*, publisher: str, title: str, date: str,
                    url: str | None = None, pages: list[int] | None = None,
                    asset_class: str | None = None) -> str:
    """Register a research report. Returns source_id. Idempotent on (publisher, title, date)."""

def upsert_entity(
    *, id: str | None = None,        # if None, derived from kind + labels[0]
    kind: EntityKind,
    labels: list[str],
    aliases: list[str] | None = None,
    description: str | None = None,
    facets: FacetSet | None = None,
    attributes: dict | None = None,
    source_ref: ProvenanceRef,
) -> dict:
    """Insert or merge an entity. Returns {entity_id, action: 'created'|'updated'|'unchanged', diff}."""

def set_attribute(entity_id: str, key: str, value, *,
                  source_ref: ProvenanceRef) -> dict:
    """Set a single attribute. Versioned. Append previous value to attribute history."""

def add_alias(entity_id: str, alias: str, *,
              source_ref: ProvenanceRef) -> dict:
    """Add an alias (e.g., learned a new ticker / Chinese name)."""

def add_facet_value(entity_id: str, facet_name: str, value: str, *,
                    source_ref: ProvenanceRef) -> dict:
    """Append a value to a facet list (e.g., headquartered_in: TW)."""

def deprecate_entity(entity_id: str, reason: str, *,
                     source_ref: ProvenanceRef) -> dict:
    """Soft-delete. Keep entity in graph but mark deprecated."""
```

### 10.3 Relation Write

```python
def upsert_relation(
    *, type: RelationType,
    source_id: str, target_id: str,
    weights: WeightCell | None = None,    # single observation; appended to time series
    attributes: dict | None = None,
    source_ref: ProvenanceRef,
) -> dict:
    """Insert or merge a relation. Dedupe on (type, source_id, target_id, period)."""

def add_weight_observation(relation_id: str, weight: WeightCell, *,
                           source_ref: ProvenanceRef) -> dict:
    """Append a new period's weight observation (time series)."""

def deprecate_relation(relation_id: str, reason: str, *,
                       source_ref: ProvenanceRef) -> dict:
    """Soft-delete."""
```

### 10.4 Analysis Write (shinkai alpha)

```python
def add_bottleneck(
    *, type: Literal["capacity", "geopolitical", "technology", "demand", "regulation"],
    severity: Literal["high", "medium", "low"],
    description: str,
    affects: list[str],                   # company ids
    at_layer: str | None = None,
    at_company: str | None = None,
    expected_resolution: str | None = None,
    source_ref: ProvenanceRef,
) -> str:
    """Register a bottleneck. Returns bottleneck_id. Auto-creates `affects` + `bottleneck_at` relations."""

def update_bottleneck(bottleneck_id: str, *,
                      severity: str | None = None,
                      status: Literal["active", "resolved", "monitoring"] | None = None,
                      description: str | None = None,
                      source_ref: ProvenanceRef) -> dict:
    """Update existing bottleneck state."""

def add_key_data(
    *, subject_id: str,
    metric: str,
    value: str,
    value_numeric: float | None = None,
    unit: str | None = None,
    period: str,
    source_ref: ProvenanceRef,
) -> str:
    """Register a quantitative fact. Returns kdp_id."""

def add_investment_thesis(
    *, target_id: str,
    stocks_to_watch: list[dict],          # [{ticker, rationale, pt?, conviction?}]
    bias: Literal["bullish", "constructive", "cautious", "bearish"],
    horizon: Literal["short", "medium", "long"],
    rationale: str,
    source_ref: ProvenanceRef,
) -> str:
    """Register an investment thesis. Returns thesis_id."""
```

### 10.5 Snapshot / Audit

```python
def create_snapshot(rationale: str, *,
                    run_id: str | None = None) -> str:
    """Commit pending changes into a new snapshot. Returns snapshot version."""

def diff_snapshots(v1: int, v2: int) -> dict:
    """Return changeset between two snapshots."""

def revert_to(snapshot_version: int, *, rationale: str) -> str:
    """Roll back to a prior snapshot. Creates a new snapshot recording the revert."""

def list_recent_changes(*, since: datetime | None = None,
                        by_run_id: str | None = None,
                        limit: int = 100) -> list[dict]:
    """Audit log query."""
```

### 10.6 LLM Tool Definitions

Each function tool exports a JSON Schema for OpenAI / Anthropic tool calling:

```python
# Auto-generated via Pydantic introspection
TOOL_DEFINITIONS = {
    "upsert_entity": {
        "name": "upsert_entity",
        "description": "Insert or merge an entity into the industry graph...",
        "input_schema": UpsertEntityInput.model_json_schema(),
    },
    # ...
}
```

Used in agent harness when binding LLM to tools.

---

## 11. Agent Ingestion Walkthrough

Example: ingest MS 20260508 "Build for future AI infrastructure" (a full research report) into the industry graph.

```python
# Step 1: register the source
src_id = register_source(
    publisher="MS",
    title="Build for future AI infrastructure - CPU, GPU, ASIC, Optical, and China chips",
    date="2026-05-08",
    pages=[2, 13, 15, 18, 29, 31, 38, 42, 49],
    asset_class="equity",
)
# returns src:ms_20260508

# Step 2: extract entities mentioned
# Agent reads PDF, identifies entities like NVDA, TSMC, Amkor, ASE, ...
for company_extracted in extracted_companies:
    upsert_entity(
        kind="Company",
        labels=company_extracted.names,
        aliases=[company_extracted.ticker, ...],
        description=company_extracted.description,
        facets=FacetSet(
            sectors=["Semiconductor"],
            regions=[company_extracted.hq_country],
            chain_layers=[company_extracted.value_chain_position],
        ),
        attributes={
            "ticker": company_extracted.ticker,
            "market_cap_usd_bn": company_extracted.mcap,
        },
        source_ref=ProvenanceRef(
            source_id=src_id, page=18, confidence=0.95, evidence_type="hard_data",
        ),
    )

# Step 3: extract supplies_to relations
for rel in extracted_supply_relations:
    upsert_relation(
        type="supplies_to",
        source_id=rel.supplier_id,           # co:TSMC
        target_id=rel.buyer_id,              # co:NVDA
        weights=WeightCell(
            period="2026",
            values={
                "buyer_spend": rel.share_of_buyer_spend,
                "seller_revenue": rel.share_of_seller_rev,
                "lock_in": rel.lock_in_score,
            },
        ),
        source_ref=ProvenanceRef(source_id=src_id, page=13, ...),
    )

# Step 4: extract bottlenecks (core alpha)
for bn in extracted_bottlenecks:
    add_bottleneck(
        type=bn.type,                        # "capacity"
        severity=bn.severity,                # "high"
        description=bn.text,                 # "TSMC CoWoS is the gating constraint..."
        affects=["co:NVDA", "co:AMD", "co:Broadcom"],
        at_layer="lay:advanced_packaging",
        at_company="co:TSMC",
        source_ref=ProvenanceRef(source_id=src_id, page=13, ...),
    )

# Step 5: extract key data points
for kdp in extracted_key_data:
    add_key_data(
        subject_id=kdp.subject,
        metric=kdp.metric,                   # "CoWoS wafer allocation"
        value=kdp.value_text,                # "875k wafers"
        value_numeric=kdp.value_numeric,     # 875000
        unit="wafers",
        period="2026e",
        source_ref=ProvenanceRef(source_id=src_id, page=13, ...),
    )

# Step 6: extract investment thesis if present
add_investment_thesis(
    target_id="co:NVDA",
    stocks_to_watch=[
        {"ticker": "2330.TW", "rationale": "Necessary CoWoS exposure", "pt": "NT$2588"},
        {"ticker": "000660.KS", "rationale": "HBM primary"},
        {"ticker": "3711.TW", "rationale": "OSAT CoWoS-R packaging"},
    ],
    bias="constructive",
    horizon="medium",
    rationale="NVDA dominance in AI infra creates necessary upstream exposures.",
    source_ref=ProvenanceRef(source_id=src_id, page=3, ...),
)

# Step 7: commit
snap_id = create_snapshot(
    rationale="Ingested MS 20260508 — NVDA AI infrastructure atlas",
    run_id="run_abc123",
)
# returns version 42 (or whatever)
```

The agent sees the full toolkit and decides which tool to call at each step. Each call returns a `diff` the agent can inspect for self-verification. If anything goes wrong, `revert_to(prev_snap)` rolls back.

---

## 12. Extension Points

How to extend without breaking existing data:

| What you want to add | How |
|---|---|
| New `kind` (e.g., `Patent`, `Standard`) | Add to `EntityKind` literal. Old data unaffected. |
| New facet (e.g., `funding_stage`, `esg_score`) | Add to `FacetSet` *or* drop into `attributes`. `extra="allow"` config means no break. |
| New relation type (e.g., `regulated_by`, `funded_by`) | Add to `RelationType` literal + define expected weight keys. |
| New weight dimension on existing relation (e.g., `tech_debt_score` on `supplies_to`) | Just add key to `WeightCell.values`. Schema is dict — open. |
| New attribute on `Bottleneck` (e.g., `monitoring_url`) | Add to `attributes`. No schema change. |
| New analysis kind (e.g., `Catalyst`, `Risk`, `Hypothesis`) | New entity kind + related relations. |
| New target (e.g., new theme `Quantum`) | Just create a Theme entity + a `targets/QUANTUM.json` shard. |
| New facet axis entirely (e.g., `ESG`) | Either: facets.esg subfield, or new entity kind `ESGRating`, or just attributes. |

**Anti-patterns** (will require migration):
- Renaming an `EntityKind` value (breaks IDs and references).
- Changing the meaning of a relation type (use new type instead).
- Moving a field from `attributes` to top-level (use a one-shot migration script).

---

## 13. V0 → V1+ Roadmap

| Version | Capability | Trigger |
|---|---|---|
| V0 | JSON files + in-memory index + Pydantic + file lock. Single user. Linear snapshots. | Now |
| V0.5 | Add SQLite derived index for cross-shard SQL queries. Whoosh fulltext on disk. | When fulltext / cross-target aggregation slows down. |
| V1 | Multi-user via WAL or queue-based writer. Snapshot DAG (branches + merges). | Team collaboration. |
| V1.5 | Migrate to Postgres + JSONB. SQLAlchemy + Alembic. | Concurrent writes exceed file-lock viability. |
| V2 | Add Apache AGE / Neo4j layer for native Cypher queries. | Graph algorithms become performance critical. |

Every transition is **non-destructive** — earlier JSON / SQL exports remain valid.

---

## 14. Open Questions (Defer to V1)

- Multi-language labels: `labels` is a list of strings now. Future: structured `{"en": "NVIDIA", "zh": "英伟达"}`?
- Confidence aggregation: when multiple sources support the same fact with different confidences, how to combine? (Bayesian, max, weighted average?)
- Temporal validity: should facts have `valid_from` / `valid_until`? Bottlenecks have `status` but not explicit time bounds.
- Multi-target snapshots: can a single agent run change multiple target shards atomically? (Yes via single snapshot, but conceptually how to scope?)

---

## 15. Implementation Plan

Once this design is approved:

1. **Pydantic models** → `services/api/src/shinkai_api/industry_graph/schemas/` (~1 day)
2. **File store + lock + audit log** → `industry_graph/store/file_store.py` (~1 day)
3. **In-memory index + NetworkX integration** → `industry_graph/store/memory_index.py` (~1 day)
4. **Snapshot diff + reconstruction** → `industry_graph/store/snapshot.py` (~1-2 days)
5. **25 function tools** → `industry_graph/tools/` (~2-3 days)
6. **LLM tool definitions auto-generated** → `industry_graph/service.py` (~0.5 day)
7. **Ingestion agent harness wiring** → integrate with shinkai's existing `agent/harness.py` (~1-2 days)
8. **Replace `industry-graph-demo.html` mock data with real query against the store** (~1 day)
9. **Smoke test: ingest MS 20260508 → demo shows real NVDA atlas** (~1 day)

Total ~10-12 dev-days for V0 first-class.

---

## 16. Relation to Existing Codebase

- Lives alongside `research-graph-schema-v0.md` — both produce graphs, with different semantics.
- Reuses `Source` / `Provenance` types (refactor common pieces into shared module).
- Snapshots integrate with shinkai's existing `Run` / event-stream model: a Run can emit `industry_graph_changed` events tied to a snapshot version.
- Mode B's Frontier Queue can query `find_bottlenecks` / `find_key_data` to enrich its discovery process.

---

**End of V0 spec.**

Audit checklist (review before approving):
- [ ] Entity kinds cover all current data in `supply_chain_graph.json`? (counter-check by mapping each field)
- [ ] Relation types capture all observed connections?
- [ ] `attributes` extension model handles unknown future fields without code change?
- [ ] File sharding strategy is intuitive for agents (one anchor = one file)?
- [ ] Snapshot diff is small enough that history is cheap?
- [ ] Function tool granularity is right (agent has control, but not too many calls per fact)?
- [ ] Provenance is mandatory at every write surface?
- [ ] In-memory footprint is acceptable at forecast scale?
