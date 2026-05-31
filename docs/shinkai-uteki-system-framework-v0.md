# Shinkai × Uteki · Agent System Framework v0

> **状态**:V0 系统框架草案
> **目标**:定义 shinkai 与 uteki 作为两个 Agent 系统时的共享平台层、职责边界、前后端契约、A2A 通信和自我改进闭环。

---

## 0. 核心判断

shinkai 和 uteki 不应被设计成两个互相聊天的 LLM bot,而应设计成两个共享 Agent Platform Core 的投研系统:

```
Agent = Model + Harness

Shared Agent Platform Core
  ├─ Run / Event / Artifact / Tool / Memory / Eval / Evolution
  ├─ OpenAPI + shared types
  ├─ Frontend live rendering primitives
  └─ A2A message envelope

Domain Agents
  ├─ uteki   = monitoring / thesis maintenance
  └─ shinkai = discovery / company analysis / handoff
```

uteki 已经有可运行的工程原型:FastAPI、Next.js、`AgentHarness`、`AgentEvent`、`RunStore`、skill version、eval、triggers、MCP。shinkai 应复用这些不变量,并在长时间运行、Research Graph、checkpoint、A2A 和 trace-native eval 上加厚。

---

## 1. 职责边界

| 系统 | 主任务 | 典型入口 | 主要产物 |
|---|---|---|---|
| **uteki** | 持续跟踪已知公司和 thesis | watchlist、财报、新闻、价格事件、用户提问 | thesis update、alert、recap、monitoring feedback |
| **shinkai** | 从主题和宏观叙事中发现水下高质量公司 | theme、market、constraints、budget | candidate handoff、Research Graph、initial thesis、eval report |

流水线关系:

```
shinkai discovers
→ shinkai underwrites
→ human approves
→ uteki monitors
→ uteki feeds back
→ shinkai improves filters / checklist / memory
```

shinkai 负责"第一次发现和公司深度分析";uteki 负责"长期跟踪和 thesis 维护"。

---

## 2. Shared Agent Platform Core

共享平台层吸收 uteki 已有模式,并成为两个系统的共同工程底座。

### 2.1 Run

一切执行都是 Run。无论来源是用户、定时任务、事件、eval、compare、A2A,最终都写入同一种 Run 记录。

基础字段:

```typescript
type Run = {
  id: string;
  owner_agent: "shinkai" | "uteki";
  user_id: string;
  kind: string;                 // chat, monitor, discovery, company_analysis, eval...
  status: RunStatus;
  triggered_by: "user" | "cron" | "event" | "eval" | "compare" | "a2a";
  trigger_reason: string;
  started_at: string;
  ended_at?: string;
  events: AgentEvent[];
  artifacts: ArtifactRef[];
  usage_summary: UsageSummary;
};
```

shinkai 扩展字段:

```typescript
type ShinkaiRun = Run & {
  mode: "mode_a_company" | "mode_b_narrative";
  lifecycle_stage: ShinkaiLifecycleStage;
  parent_run_id?: string;
  child_run_ids: string[];
  graph_id?: string;
  checklist_ref: string;
  budget: BudgetSpec;
};
```

### 2.2 Event

前端渲染、回放、评测、审计全部基于单一事件流。

uteki 现有事件可保留:

```text
run_start, plan, step_start, step_end, thinking,
tool_call, tool_result, delta, citation, usage,
log, artifact_written, await_review, error, done
```

shinkai 需要新增:

```text
section_started
section_completed
item_started
item_completed
item_inconclusive
graph_delta
evidence_found
claim_created
claim_updated
question_opened
critic_warning
checkpoint_raised
checkpoint_released
eval_completed
a2a_message_sent
a2a_message_received
```

约束:任何 emit 给前端的事件必须先持久化。回放结果必须与实时观看一致。

### 2.3 Artifact

Artifact 是大对象和跨 Agent 交接载体。

常见类型:

```text
markdown_report
research_graph_snapshot
research_graph_diff
eval_report
candidate_list
filing_extract
checkpoint_packet
a2a_payload
```

### 2.4 Tool

工具协议沿用 uteki 的 `Tool` 模型:名称、描述、JSON schema 参数、结构化结果。

共享工具:

```text
web_search
web_extract
financials
market_quote
news_search
report_analysis
compute
```

shinkai 专用工具:

```text
sec_fetch
transcript_fetch
graph_query
graph_write
theme_dependency_traversal
mark_item_status
```

治理规则:skill 不直接执行 IO,只表达 tool intent;harness 负责 dispatch、限流、timeout、审计和错误处理。

### 2.5 Evolution

继承 uteki 的 skill signature 思路,但 shinkai 的版本签名应包括:

```typescript
type AgentSignature = {
  prompt: string;
  model: string;
  params: object;
  tool_names: string[];
  checklist_refs: string[];
  filter_policy_refs: string[];   // Q1 / Q2
  context_policy_ref: string;
  eval_policy_ref: string;
};
```

每条 Run 绑定当时的 signature version,用于纵向比较。

---

## 3. Shinkai Specialized Harness

shinkai 是长跑 Agent,不能只用 chat harness。它需要 `Run → Section → Item → Step` 的确定性外壳。

### 3.1 Lifecycle

```text
created
→ scoped
→ theme_framing
→ graph_expansion
→ candidate_discovery
→ quality_filtering
→ underwater_filtering
→ company_analysis
→ cross_candidate_comparison
→ critic_review
→ human_review
→ memory_update
→ handoff
→ completed
```

中断状态:

```text
paused
awaiting_checkpoint
failed
recovering
aborted
```

### 3.2 Deterministic Outer Loop

harness 决定"做什么",model 只决定"如何完成当前 item"。

```
RunController
  → ChecklistEngine selects next item
  → ContextBuilder builds model-visible state
  → Model proposes action
  → Harness validates action
  → ToolRegistry executes
  → GraphStore / EventStore persist
  → DoneVerifier checks item completion
```

这保证 shinkai 不会在长时间运行中忘记 checklist、跳过反方证据或无限搜索。

### 3.3 Research Graph as State

shinkai 的事实源不是最终报告,而是 Research Graph。

Graph 存:

```text
Entity, Claim, Evidence, Question, Thesis
Structural / Evidential / Logical / Temporal edges
confidence, source, decay, last_verified_at
```

ContextBuilder 每一步从 graph 拉取相关子图,而不是依赖压缩后的聊天历史。

---

## 4. Frontend / Backend Contract

前端不直接理解 Agent 内部实现,只消费四类资源:

```text
Run summary
Event stream
Artifacts
Graph / subgraph
```

核心接口:

```text
POST   /api/v1/runs
GET    /api/v1/runs
GET    /api/v1/runs/{id}
GET    /api/v1/runs/{id}/events        SSE
POST   /api/v1/runs/{id}/pause
POST   /api/v1/runs/{id}/resume
POST   /api/v1/runs/{id}/abort
POST   /api/v1/runs/{id}/inject

GET    /api/v1/runs/{id}/graph
GET    /api/v1/runs/{id}/graph/subgraph
GET    /api/v1/runs/{id}/artifacts
GET    /api/v1/runs/{id}/report

GET    /api/v1/checkpoints/{id}
POST   /api/v1/checkpoints/{id}/release
```

Web 首屏:

```text
/runs                 Run 列表
/runs/new             启动 Mode A / Mode B
/runs/[id]            live dashboard
/runs/[id]/review     checkpoint review
/runs/[id]/report     report + graph export
/eval                 eval reports
/a2a                  agent messages / handoffs
```

UI 原则:

- live dashboard 以 SSE 为默认,不轮询。
- Event stream 是产品 UI,不是调试日志。
- Checkpoint review 是最高优先级交互。
- Graph viewer 与 event stream 联动:点击事件可定位 graph delta。

---

## 5. A2A Protocol

A2A 传结构化研究对象,不传自由聊天文本。

### 5.1 Envelope

```typescript
type AgentMessage = {
  message_id: string;
  schema_version: string;
  from_agent: "shinkai" | "uteki";
  to_agent: "shinkai" | "uteki";
  type: AgentMessageType;
  created_at: string;
  correlation_id: string;       // run_id / thesis_id / graph_id
  priority: "low" | "normal" | "high";
  requires_ack: boolean;
  status: "queued" | "delivered" | "acked" | "processed" | "failed";
  payload: object;
};
```

### 5.2 V0 Message Types

```text
candidate_handoff        shinkai → uteki
thesis_update            either direction
challenge_claim          uteki → shinkai
monitoring_feedback      uteki → shinkai
memory_patch_proposal    either direction
checklist_patch_proposal shinkai internal / uteki feedback
```

### 5.3 Candidate Handoff

```typescript
type CandidateHandoff = {
  company: { ticker: string; name: string; cik?: string };
  theme: string;
  discovered_from_run_id: string;
  research_graph_ref: string;
  initial_thesis_ref: string;
  quality_score: number;
  underwater_score: number;
  confidence: number;
  monitoring_triggers: string[];
  kill_criteria: string[];
  unresolved_questions: string[];
};
```

### 5.4 Monitoring Feedback

```typescript
type MonitoringFeedback = {
  company: { ticker: string; name: string };
  original_thesis_ref: string;
  status: "thesis_strengthened" | "thesis_weakened" | "thesis_broken" | "unchanged";
  evidence_refs: string[];
  reason: string;
  suggested_rule_update?: string;
  suggested_checklist_patch?: string;
};
```

治理规则:

- Agent 可以 propose,不能直接批准关键变更。
- 加入 uteki 正式 watchlist 需要 human approval。
- checklist / memory patch 需要 human approval。
- 所有 A2A 消息写 audit log。

---

## 6. Eval and Self-Improvement Loop

shinkai 的 eval 必须以 trace 为原始材料,不是只评最终报告。

### 6.1 Eval Layers

| 层 | 输入 | 检查 |
|---|---|---|
| Process Eval | events + lifecycle | 是否按 checklist 完成、是否超预算、是否卡住 |
| Evidence Eval | Evidence nodes + sources | 证据是否存在、可靠、支持 claim |
| Reasoning Eval | claim graph + thesis | 因果链是否成立、反方证据是否处理 |
| Discovery Eval | candidates + filters | 是否真的高质量且水下 |
| Outcome Eval | uteki feedback | thesis 是否存活、风险是否兑现 |

### 6.2 Improvement Outputs

每次完整 run 结束后生成:

```text
eval_report
failure_report
research_memory_patch
failure_memory_patch
checklist_patch_proposal
filter_policy_patch_proposal
```

这些 patch 默认都是 proposal。只有 human 或 policy engine 批准后才进入正式版本。

---

## 7. Implementation Plan

### Phase 0 · Align Core

- 对齐 uteki 的 Run / Event / Tool / Artifact / Evolution schema。
- 定义 shinkai 专用 event type。
- 定义 A2A envelope。
- 建立 OpenAPI → shared types 生成链路。

### Phase 1 · Shinkai Vertical Slice

- `POST /runs` 启动一个 Mode A demo run。
- Run 产生 section/item/tool/graph_delta 事件。
- 前端 live dashboard 能实时渲染 event stream。
- GraphStore 能写入 Entity / Claim / Evidence。

### Phase 2 · Checkpoint and Eval

- 支持阻塞 checkpoint。
- 支持 checkpoint review UI。
- 生成 Process / Evidence / Reasoning eval report。

### Phase 3 · Mode B Discovery

- 实现主题图谱扩展。
- 实现 Q1/Q2 过滤。
- 自动触发多个 Mode A child runs。
- 生成 candidate comparison。

### Phase 4 · Uteki A2A

- shinkai 发送 `candidate_handoff`。
- uteki 接收为 watch candidate。
- uteki 发送 `monitoring_feedback`。
- shinkai 生成 memory/checklist/filter patch proposal。

---

## 8. Non-Goals for V0

- 不做自由多 Agent 群聊。
- 不允许 Agent 自动修改正式 checklist。
- 不允许 shinkai 直接写入 uteki 正式 watchlist。
- 不做复杂 message broker;V0 用 Postgres `agent_messages` 表即可。
- 不追求全自动交易或组合管理。

---

## 9. Key Invariants

1. 一切执行都是 Run。
2. 一切可见行为都是 Event。
3. Event 先持久化,再推给前端。
4. Tool IO 只能由 harness 执行。
5. shinkai 的长期状态在 Research Graph,不在聊天历史。
6. Eval 从 trace 和 graph 生成,不是只读最终报告。
7. A2A 传结构化对象,不传自由聊天。
8. Agent 可以提出变更,关键变更必须审批。
