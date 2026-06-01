# Hypothesis Card v0 — Data Contract

Status: **active, V0** (Path A, 2026-06-01).

This document fixes the data contract behind the `<HypothesisCard />` and
`<FrontierQueueCard />` components in the cockpit, so the frontend and the
agent harness can evolve independently without breaking each other.

## 1. Hypothesis

A `Hypothesis` is the agent's first-class commitment for a given supply-chain
layer (Mode B) or company anchor (Mode A). Each layer that the harness expands
emits exactly one hypothesis. The hypothesis lives in `research_store` and is
addressable by `hypothesis_id`.

```ts
type HypothesisState = "active" | "falsified" | "superseded";

type ConfidenceChangeKind = "support" | "contradict" | "human_correction";

type ConfidencePoint = {
  ts: number;                         // POSIX seconds UTC
  confidence: number;                 // 0..1, post-update
  delta: number;                      // round(new - prev, 4)
  evidence_id: string;                // links to Evidence.evidence_id,
                                      // or "inject_<event_id>" for human_correction,
                                      // or "falsification" when manually falsified
  kind: ConfidenceChangeKind;
  method: string;                     // see §3
};

type Hypothesis = {
  hypothesis_id: string;              // _stable_id("hyp", run_id, layer.name)
  run_id: string;
  layer: string;                      // SupplyChainLayer.name
  claim: string;                      // human-readable statement
  confidence: number;                 // 0..1, latest
  state: HypothesisState;
  falsification_condition: string;    // plain-text (see §4)
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  confidence_history: ConfidencePoint[];
  superseded_by_id: string | null;
};
```

Source: `services/api/src/shinkai_api/research/models.py`.

## 2. Events

The harness emits four hypothesis-typed events. Each one carries enough data
that the UI can render without round-tripping to the hypotheses endpoint.

### `hypothesis_created`

```json
{
  "hypothesis_id": "hyp_power_and_electric_..._a1b2c3d4e5f6",
  "layer": "Power and electrical infrastructure",
  "claim": "Power and electrical infrastructure is a candidate ...",
  "initial_confidence": 0.5,
  "falsification_condition": "Two independent primary sources refute ..."
}
```

Emitted right before the matching `judgment_created` event so the UI can show
a hypothesis card the moment the agent commits to a layer.

### `hypothesis_confidence_updated`

```json
{
  "hypothesis_id": "...",
  "prev_confidence": 0.5,
  "new_confidence": 0.575,
  "delta": 0.075,
  "evidence_id": "evidence_...",
  "kind": "support",
  "method": "evidence_weighted_average_v0"
}
```

The harness emits one event per supporting/contradicting evidence record, and
the `_consume_pending_injections` helper emits one with `kind: "human_correction"`
when a `correction` injection is processed.

### `hypothesis_falsified`

```json
{
  "hypothesis_id": "...",
  "trigger": "manual",            // V0: only "manual" is used
  "reason": "human review found two independent refuting sources"
}
```

Reserved. Not emitted automatically in V0 — falsification is human-driven.

### `hypothesis_superseded`

```json
{
  "hypothesis_id": "...",
  "replaced_by_id": "hyp_...",
  "reason": "next-spiral hypothesis subsumes this one"
}
```

Reserved. Not emitted in V0.

## 3. Confidence algorithm (`method` field)

V0 algorithm is identified by the string `evidence_weighted_average_v0`:

```
weight = clamp(reliability_score, 0, 1) * 0.15
delta  = +weight  (support)
       | -weight  (contradict)
       | -0.15    (human_correction)
new_confidence = clamp(prev_confidence + delta, 0, 1)
```

Where `reliability_score` comes from `research.models.source_reliability_score`
(tier-based: primary ≈ 0.9, secondary ≈ 0.72, tertiary ≈ 0.56,
agent_inference = 0.2).

### Why a `method` field

Storing `method` on every `ConfidencePoint` and every
`hypothesis_confidence_updated` event lets the harness swap the algorithm
without a breaking change for downstream consumers — they can branch on
`method` to render or interpret correctly. Possible future values:

- `bayesian_v0` — proper prior + likelihood update once each evidence kind
  carries a calibrated likelihood.
- `manual_override_v0` — a human-pinned value, bypassing the auto-update.

## 4. Falsification condition

V0 chose plain text on purpose. There is no DSL, and the agent will not
automatically detect falsification — falsification is a human review action
triggered via the `correction` injection or a future explicit endpoint.

The text is generated at hypothesis creation time from the layer's
`next_frontier`, following the template:

> "Two independent primary sources refute the claim that <layer> is structurally
> constrained, OR the layer's next frontier (<next_frontier>) yields no
> supplier improvement signal."

V1 candidates: DSL expression that ties into financial data (e.g.
`gross_margin < 0.15 for 4 quarters`) once a real fundamentals data feed is
integrated.

## 5. API

`GET /api/v1/runs/{run_id}/hypotheses` returns `Hypothesis[]` sorted by
`hypothesis_id`. The full `confidence_history` is included; clients should
expect lists of 10–100 points for a completed Mode B run.

No pagination, no filtering — hypothesis count per run is bounded (one per
layer, currently 4 for the default supply-chain layers).

## 6. Frontend rendering contract

The `<HypothesisCard />` component:

- Loads hypotheses from the endpoint above on mount and whenever
  `refreshSignal` (typically `events.length`) changes.
- Renders a hand-rolled SVG sparkline of `confidence_history`. Per-point
  markers are colored by `kind`: green for `support`, red for `contradict`,
  orange for `human_correction`.
- Shows a left/right pager when there are multiple hypotheses.
- Falsification condition is displayed in a callout block.
- The card's outer `<section>` gets `id={"hypothesis-${hypothesis_id}"}` so
  `<InjectionHistory />` can scroll to it via `effect_link`.

The `<FrontierQueueCard />` component:

- Derives queue state from events (no separate endpoint).
- Three columns: queued, running, completed.
- Items colored by `source`: planner (blue), reviewer (purple),
  human_injection (orange).

## 7. Recovery semantics

- Hypothesis state IS persisted via `research_store` — `confidence_history`
  survives run recovery.
- The frontier queue and `filter_policy_patches` are in-memory only —
  injection effects on those are lost on recovery. (V1 work: persist scope
  mutations through a new `default_run_store.mutate_scope` helper.)
