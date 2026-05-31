# Autonomous AI Supply Chain Discovery v0

> **状态**:V0 implementation spec
> **目标**:让 shinkai 自主围绕 AI 主题、完整产业链和供应链,从超大型共识公司向下不断发掘核心环节的关键公司,并以 review → optimize loop 持续改进。

---

## 0. Operating Thesis

shinkai 的目标不是回答一次问题,而是持续运行一个投研发现循环:

```text
Seed giants
→ expand AI supply-chain layers
→ identify bottleneck nodes
→ surface key companies
→ score quality / underwater fit
→ review evidence and reasoning
→ optimize next search frontier
→ repeat until objective met or budget exhausted
```

V0 的成功标准:系统能自主产出可观测事件、Research Graph 节点/边、候选公司队列、review finding 和下一轮优化 frontier。

---

## 1. Seed and Expansion Model

起点是超大型共识公司:

```text
NVIDIA, Microsoft, Amazon, Google, Meta, TSMC, Broadcom, ASML
```

shinkai 从它们向下扩展:

| Layer | 示例问题 | 输出 |
|---|---|---|
| Compute | 谁提供 GPU / ASIC / accelerator 周边能力? | accelerator, ASIC, board, server vendors |
| Packaging | 谁解决先进封装、HBM、substrate、test 瓶颈? | OSAT, metrology, probe, handlers |
| Power | 谁解决 power delivery、backup、grid interconnect? | electrical equipment, UPS, switchgear |
| Cooling | 谁解决 liquid cooling、thermal density? | thermal management, CDUs, facility systems |
| Networking | 谁解决 east-west traffic、optics、switching? | optical, DSP, cables, switches |
| Data Center | 谁建造、运营、维护 AI DC? | colocation, EPC, equipment |
| Software Infra | 谁支持 observability、security、deployment? | infra software, networking software |

每轮 expansion 必须产生:

- frontier node
- bottleneck claim
- evidence placeholder or source
- candidate companies
- next questions

---

## 2. Review → Optimize Loop

每轮 loop 有固定结构:

```text
1. plan_frontier
2. expand_layer
3. create_claims
4. surface_candidates
5. score_candidates
6. review_trace
7. optimize_frontier
```

### Review

检查:

- 是否从共识公司向下扩展,而不是停留在一线公司。
- 每个候选是否绑定明确 bottleneck。
- 是否区分事实、推断和观点。
- 是否有 evidence gap。
- 是否有下一轮可执行问题。

### Optimize

根据 review 输出下一轮策略:

- 加深某个 layer。
- 改换 seed giant。
- 排除过于共识的公司。
- 强化 Q1 质量过滤。
- 强化 Q2 underwater 过滤。

---

## 3. Observability Contract

必须输出这些事件:

```text
supply_chain_layer_started
frontier_expanded
theme_discovered
evidence_found
claim_created
judgment_created
candidate_created
candidate_scored
review_completed
optimization_decision
research_task_created
graph_delta
eval_completed
```

每个事件必须携带:

- `run_id`
- `loop_index`
- `layer`
- `source_refs` where available
- `confidence`
- `next_action` where applicable

---

## 4. Data Contract

Research Graph 是长期状态:

```text
Entity: giant, layer, company, bottleneck, product
Claim: bottleneck claim, quality claim, underwater claim
Evidence: source, excerpt, reliability
Question: unresolved next research question
Thesis: candidate-level thesis
```

边:

```text
supplies_to
depends_on
participates_in
supports
contradicts
decomposes_into
```

---

## 5. Spiral Plan

### Spiral 1

Synthetic but structured loop. No external LLM required. Goal: event/graph/UI contract.

### Spiral 2

Add real web search and extraction. Goal: evidence-backed layer expansion.

Implemented acceptance target:

- `allow_live_sources=true` makes each layer call `web_search`.
- Successful search results create `Evidence` nodes with `source_uri`,
  `source_title`, `excerpt`, reliability, and `source-backed` tags.
- Review score reflects source quality.
- If live evidence fails, the loop remains runnable and emits an explicit
  evidence gap instead of failing silently.
- Tests cover both deterministic fallback and source-backed evidence paths.

### Spiral 3

Add optional LLM planner through direct DeepSeek API.

Runtime config:

```bash
export SHINKAI_DEEPSEEK_API_KEY="..."
export SHINKAI_LLM_MODEL="deepseek-chat"
```

Goal: model proposes frontier and review findings, harness validates. The key
must remain runtime-only and must not be committed to repo files.

### Spiral 4

Add Q1/Q2 scoring and Mode A child runs. Goal: candidate queue becomes actionable.

### Spiral 5

Add uteki handoff and monitoring feedback. Goal: outcome feedback improves shinkai filters and checklist.
