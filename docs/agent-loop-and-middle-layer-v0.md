# Shinkai · Agent Loop + Middle Layer · V0 Design

> **时间**:2026-05-27
> **状态**:V0 架构设计(等用户 review / 修订)
> **配套**:`alignment-v2.md` §11(架构骨架)、`research-graph-schema-v0.md`(数据模型)、`checklists/value-investing-v1.md`(Mode A 执行清单)

本文档定义 V0 的两个最关键运行机制:
- **B · Agent Loop** — Agent 实际怎么"思考-行动-写图谱-检查-推进"
- **C · Middle Layer** — 人怎么"看见-控制-审阅-审计" Agent

两者是同一个系统的两面,设计上必须互锁。

---

## 0. 设计原则回顾(从 alignment-v2 拉过来,作为本文档的约束)

每个设计决策必须满足:
- **P1** Agent 在自己执行环境跑,中间层提供 observe/steer/audit
- **P2** 工具极简(≤ 10)
- **P3** 资源投在核心层(eval, critic, memory, iteration)
- **P4** 单 Agent,不做多 Agent 协作
- **P5** **每个组件必须可观测 + 可评测**

---

# Part B · Agent Loop

## B1. 三层循环架构

Agent loop 是**层级状态机**,不是"LLM 自由 ReAct"。

```
┌─────────────────────────────────────────────────────────┐
│  RUN LEVEL                                              │
│  ─────────                                              │
│  生命周期: started → running → (paused | checkpoint)*  │
│                  → completed | failed | aborted         │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ITEM LEVEL  (一个 checklist item)               │   │
│  │  ─────────                                       │   │
│  │  生命周期: not_started → in_progress             │   │
│  │            → done | inconclusive | deferred      │   │
│  │                                                  │   │
│  │  ┌──────────────────────────────────────────┐    │   │
│  │  │  STEP LEVEL  (一次 ReAct 步)             │    │   │
│  │  │  ─────────                              │    │   │
│  │  │  thought → action → observation         │    │   │
│  │  │  (一次 LLM 调用 + 一次工具调用)          │    │   │
│  │  └──────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**核心理念**:
- **外层(Run)是确定性的** — 按 checklist 顺序推进,不让 LLM 决定"做什么"
- **中层(Item)是 LLM 驱动的** — LLM 决定"怎么做这个 item",在 budget 内迭代
- **内层(Step)是单步 ReAct** — 一次 think + 一次 tool call + 一次 observe

这个分层把 LLM 的自由度限制在**最有价值的地方**(怎么完成一个明确目标),而不让 LLM 决定"目标是什么"(那是 checklist 的工作)。

## B2. 外层 Run Loop(伪代码)

```python
def run_loop(run_spec: RunSpec):
    emit("run.started", run_spec)

    checklist = load_checklist(run_spec.mode)        # Mode A 或 Mode B
    scoped_items = scope_checklist(
        checklist,
        section_0_inputs=run_spec.scoping,           # 用户填的 Section 0
        depth_tier=run_spec.depth,                   # shallow / standard / deep
    )

    for section in scoped_items.sections:
        emit("section.started", section)
        for item in section.items:
            if item.skip_per_depth_tier:
                emit("item.deferred", item)
                continue
            run_item(item)                            # → ITEM loop (B3)

        emit("section.completed", section)

        # 强制 critic + 强制人机 checkpoint
        if section.id in {3, 6}:                     # 护城河、估值后
            critic_pass(section)
            await_checkpoint(section)                # 阻塞,等人 review

        if section.id == 8 and item.id == "8.3":     # Kill Criteria
            await_checkpoint(item, mandatory=True)

    finalize_thesis()                                # 综合 Section 8 产出 Thesis 节点
    emit("run.completed")
```

**关键设计**:
- Section 完成才触发 critic,不在 item 粒度触发(降低成本)
- Checkpoint **阻塞** Agent — 人不批 Agent 不动(V0 选择,后续可考虑非阻塞)
- 8.3 Kill Criteria 是**强制 checkpoint**,无 override(对应 P5)

## B3. 中层 Item Loop(伪代码)

```python
def run_item(item: ChecklistItem) -> ItemOutcome:
    emit("item.started", item)

    context = build_item_context(
        item_spec=item,                              # Why / Where / Output / Done when
        relevant_graph_subgraph=query_graph(
            related_to=item.subject_entities,
            limit_kb=20,                             # 控制上下文大小
        ),
        budget_remaining=run_budget.remaining,
    )

    for iteration in range(item.max_iterations):    # 默认 max=10
        emit("item.iteration", {"item": item.id, "n": iteration})

        # 单步 STEP loop(LLM 决策)
        decision = llm_step(context)

        match decision.type:
            case "tool_call":
                result = execute_tool(decision.tool, decision.args)
                context.append_observation(result)

            case "write_graph":
                graph_store.commit(decision.nodes, decision.edges)
                emit("graph.delta", decision.summary)

            case "mark_done":
                if verify_done_criterion(item, decision.evidence):
                    emit("item.completed", item)
                    return ItemOutcome.DONE
                else:
                    context.append_observation("done criterion not yet satisfied")

            case "ask_human":
                user_input = await_human_input(decision.question)
                context.append_observation(user_input)

            case "give_up":
                emit("item.inconclusive", {"item": item.id, "reason": decision.reason})
                return ItemOutcome.INCONCLUSIVE

    # Budget 用尽
    emit("item.inconclusive", {"item": item.id, "reason": "max_iterations"})
    return ItemOutcome.INCONCLUSIVE
```

**关键设计**:
- **Graph 是 externalized state** — Agent 不在 prompt 里携带跨 item 状态,而是写到 graph,下一 item 按需查
- **Item 都有 max_iterations**(默认 10)— 防止单 item 黑洞
- **失败 ≠ 沉默** — INCONCLUSIVE 也是有 evidence 的状态,会记录"为什么没做完"
- **ask_human 是少用但允许的工具** — 当 Agent 真卡住,允许提问;但要避免滥用

## B4. 内层 Step Loop · LLM 调用 prompt 框架

每次 step 的 prompt 长这样(简化版):

```
SYSTEM:
You are shinkai, an investment research Agent. You are working on:
  Section {n}: {section_title}
  Item {n.m}: {item_title}

Why this item matters: {item.why}
Where to look: {item.where}
What to produce: {item.output_node_types}
Done when: {item.done_when}

You have access to tools: {tool_list}

Current relevant graph state:
{compressed_subgraph}

Recent observations:
{last_n_observations}

Budget: {tokens_left}, {time_left}

USER:
Decide your next action. Output JSON:
{
  "thought": "...",
  "action_type": "tool_call" | "write_graph" | "mark_done" | "ask_human" | "give_up",
  "args": { ... }
}
```

**关键设计**:
- **结构化 prompt** — system 部分模板化,user 部分要求 JSON 输出
- **强制 thought 字段** — 这是 observability 的核心:Agent 必须解释"为什么这么做"
- **action_type 受限** — Agent 不能发明新动作

## B5. 工具集(V0,8 个,符合 P2)

| # | 工具 | 用途 | 备注 |
|---|------|------|------|
| 1 | `web_search` | 搜索网页 | 用于一般查询(Tavily / Brave / Serper 三选一) |
| 2 | `web_extract` | 抓取网页正文 | URL → 干净 markdown |
| 3 | `sec_fetch` | 拉取 SEC filing | ticker + form (10-K/10-Q/8-K/DEF14A) → 结构化文本 |
| 4 | `graph_query` | 查询研究图谱 | 按 entity / tag / claim_type 检索 |
| 5 | `graph_write` | 写入图谱(节点/边) | 原子提交,带 confidence 与 source |
| 6 | `compute` | 数值计算 | 估值倍数、ROIC、DCF 等(沙箱 Python eval) |
| 7 | `ask_human` | 向人提问 | 仅在 Agent 真卡住时;默认折扣其使用 |
| 8 | `mark_item_status` | 标记 item 完成 / 不完整 | 终结当前 item |

**关键设计**:
- **`graph_query` 和 `graph_write` 是核心** — 让 Agent 把研究状态外部化
- **没有"file_read"或"file_write"** — 一切持久化通过 graph
- **没有 critic 工具** — critic 是 system 自动触发,不是 Agent 自己调
- **8 个工具,符合 P2** — 后续若需新增,先评估能否用现有工具组合实现

## B6. 关键设计选择与权衡

| 选择 | V0 决定 | 替代方案 | 为什么这么选 |
|------|---------|----------|--------------|
| 外层是否 LLM 驱动 | **否,确定性状态机** | LLM-as-orchestrator | 防止 Agent "忘了"checklist;符合 P5(每步可观测) |
| 跨 item 状态存储 | **写入 graph** | 长上下文携带 | 防止上下文衰减;graph 本就是产物 |
| 单 item 最大迭代 | **10** | 无限 / 5 | 平衡完成率与黑洞风险;可调 |
| Checkpoint 是否阻塞 | **阻塞** | 异步队列 | V0 简单;Agent 不能在未审情况下继续 |
| Critic 触发粒度 | **section 完成时** | item 完成时 / 全跑完 | 平衡成本与反馈频次 |
| 工具结果缓存 | **按 hash 缓存** | 不缓存 / 完整重跑 | 省 token & 时间;同 URL 不重复抓 |
| Mode B 子任务 | **顺序跑 Mode A 子 run** | 并行 | V0 简单,减少上下文 / 成本峰值 |

---

# Part C · Middle Layer

## C1. 内核 + 适配器分离

```
┌───────────────────────────────────────────────────────┐
│                    Adapters                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   CLI       │  │   Web UI    │  │    API      │    │
│  │   (V0)      │  │   (V1)      │  │   (V1+)     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│         │                │                │           │
└─────────┼────────────────┼────────────────┼───────────┘
          ▼                ▼                ▼
┌───────────────────────────────────────────────────────┐
│              Middle Layer Kernel                      │
│                                                       │
│  RunController     EventBus     CheckpointGateway     │
│  InjectionChannel  GraphStore   AuditLog              │
│                                                       │
└───────────────────────────────────────────────────────┘
              │              │
              ▼              ▼
        Agent Loop      Tool Sandbox
```

**关键设计**:
- **内核形态稳定**,适配器随部署形态变化
- V0 只做 **CLI 适配器**,但内核 API 要为 Web UI / API 留好
- 这是 P1(三层架构)的工程落地

## C2. 内核组件

### `RunController`
生命周期管理:
- `start(run_spec)` → run_id
- `pause(run_id)` / `resume(run_id)`
- `stop(run_id)` — 优雅终止
- `abort(run_id)` — 强制终止
- `list_runs(filter)` / `get_run_status(run_id)`

### `EventBus`
Agent → 观察者的 pub/sub:
- 所有 Agent 决策、graph 变更、tool 调用、critic 反馈都发到 EventBus
- 多订阅者支持(CLI tail、Web UI、审计日志都是订阅者)
- 持久化(每个 event 落盘到 `runs/<run_id>/events.jsonl`)

### `CheckpointGateway`
Section 3 / 6 / 8.3 处的人机交接:
- Agent 发 `checkpoint.reached` 事件,**阻塞**
- 人在 CLI / UI 上看到当前 graph 子图,决定 `approve` / `reject` / `modify`
- 人下决定后 `release(checkpoint_id, decision)`,Agent 继续

### `InjectionChannel`
人主动推信息给 Agent:
- 用户:"我已经知道这家公司的 CEO 是前 Intel CTO,跳过 5.1"
- 注入下次 step prompt 的"user prior knowledge"字段
- 不是工具,是 Agent 被动消费的"环境信号"

### `GraphStore`
事实之源:
- 持久化每个 run 的 ResearchGraph
- 支持 `query` / `write` / `diff` / `snapshot(version)`
- V0:JSON 文件(`runs/<run_id>/graph.json`)
- V1+:可换为 Neo4j / SQLite + JSONB / 向量 DB,接口不变

### `AuditLog`
全 event + graph 历史:
- 所有 events.jsonl 永久保留
- graph 每次写入存 diff(支持时间回溯)
- 支持 `replay(run_id)` — 用同样的 scoping 重新跑

## C3. V0 CLI 适配器(命令清单)

```bash
# 项目初始化
shinkai init                                  # 初始化项目目录结构

# 启动研究
shinkai run mode-a --ticker AAPL [--depth standard]
shinkai run mode-b --theme "AI Infrastructure"

# 观察
shinkai list                                  # 列出所有 runs(状态、进度、成本)
shinkai status <run-id>                       # 当前快照
shinkai watch <run-id>                        # 实时 tail events
shinkai inspect <run-id> [--section N]        # 检视图谱内容

# 控制
shinkai pause <run-id>
shinkai resume <run-id>
shinkai abort <run-id>

# 干预
shinkai inject <run-id> --fact "..."          # 注入事实
shinkai inject <run-id> --skip-item 1.4       # 跳过指定 item
shinkai modify-checklist <run-id> --add ...   # 增删 item

# Review(checkpoint 处的人机交互)
shinkai review <run-id>                       # 进入当前 checkpoint 的交互式 review

# 高级
shinkai replay <run-id>                       # 同样 scoping 重跑
shinkai diff <run-id-a> <run-id-b>            # 对比两次 run 的 graph

# 渲染
shinkai render <run-id> [--out report.md]     # 把 graph 渲染成 Markdown 报告
```

13 个命令。覆盖 lifecycle + 观察 + 控制 + 干预 + review + 渲染。

## C4. Event 协议(共享接口)

Agent 与中间层通信的唯一形式 = events。

### Event 通用结构

```json
{
  "event_id": "evt_001",
  "run_id": "run_abc",
  "timestamp": "2026-05-27T10:00:00Z",
  "type": "item.completed",
  "data": { ... type-specific ... },
  "running_meta": {
    "tokens_used": 12000,
    "cost_usd": 0.42,
    "wall_time_sec": 180,
    "current_section": 1,
    "current_item": "1.5"
  }
}
```

### Event 类型表

| 类别 | type | 触发时点 | 主要 data 字段 |
|------|------|----------|---------------|
| Run | `run.started` | run 启动 | spec, mode |
| Run | `run.paused` / `run.resumed` | 用户控制 | reason |
| Run | `run.completed` / `run.failed` / `run.aborted` | run 结束 | summary, thesis_id (if any) |
| Section | `section.started` / `section.completed` | section 边界 | section_id |
| Item | `item.started` | item 开始 | item_id |
| Item | `item.iteration` | 每个内层 step | iteration_n, thought |
| Item | `item.completed` / `item.inconclusive` / `item.deferred` | item 结束 | reason, output_node_ids |
| Tool | `tool.called` | 调用工具前 | tool_name, args_summary |
| Tool | `tool.completed` / `tool.failed` | 调用工具后 | result_summary / error |
| Graph | `graph.delta` | 每次 write 后 | nodes_added, edges_added, nodes_updated |
| Critic | `critic.invoked` / `critic.feedback` | critic 触发 | persona, findings |
| Checkpoint | `checkpoint.reached` | 阻塞前 | section_id, graph_snapshot_id |
| Checkpoint | `checkpoint.released` | 人放行后 | decision (approve/reject/modify), comments |
| Human | `human.injection` | 用户 inject | fact / skip / modification |
| Budget | `budget.warning` | 用尽 80% | budget_type (token/time/cost) |
| Budget | `budget.exceeded` | 用尽 100% | budget_type, action_taken |

### Event 持久化

每个 run 的事件追加写入 `runs/<run_id>/events.jsonl`,**永不删除**。这是审计 + replay 的基础。

## C5. Checkpoint 交互(C 的核心 UX)

Checkpoint 是 Middle Layer 最关键的人机交接点。

### 触发时刻

| 时刻 | 触发器 | 目的 |
|------|--------|------|
| Section 3 后 | `await_checkpoint("moat_review")` | 护城河弱则提前止损 |
| Section 6 后 | `await_checkpoint("valuation_review")` | 估值是否合理买点 |
| 8.3 处 | `await_checkpoint("kill_criteria", mandatory=True)` | 评测锚点必须人确认 |

### Checkpoint 交互流程(CLI 版)

```
$ shinkai watch run_abc
[INFO] run_abc reached checkpoint: moat_review (after Section 3)
[INFO] Run paused. Use `shinkai review run_abc` to inspect & decide.

$ shinkai review run_abc
═══════════════════════════════════════════════════════
  CHECKPOINT · moat_review · Section 3 完成后
═══════════════════════════════════════════════════════

Graph subgraph (moat-related findings):

  Entity: Apple Inc.
    └─ Claims:
       · "Apple 拥有强网络效应护城河" [conf=0.82]
         ↳ Evidence: 10-K Item 1, App Store ecosystem (3 sources)
       · "切换成本被 iCloud / Apple ID 锁定" [conf=0.71]
       · "硬件设计护城河在过去 5 年扩宽" [conf=0.65]
    └─ Open Questions:
       · "Vision Pro 是否能开启下一个生态护城河?"

Critic findings (Buffett-persona):
  · 高 confidence claims 都有 ≥ 2 evidence ✓
  · 缺乏反方证据 — 是否考虑过 antitrust 风险对生态的影响?

Your decision:
  [a] Approve — continue to Section 4
  [r] Reject — abort run
  [m] Modify — inject fact / question / re-do
  [d] Show details for a specific claim

>
```

这个 UX 是 V0 的核心。人在这里**真正干预 Agent**,而不是事后看报告。

## C6. 文件系统布局(V0)

```
shinkai/
├── .shinkai/
│   ├── config.json                 # 项目配置(数据源、API keys、预算)
│   └── tools/                      # 工具实现(Python module)
├── docs/
│   ├── alignment-v2.md
│   ├── research-graph-schema-v0.md
│   ├── agent-loop-and-middle-layer-v0.md   ← 本文档
│   └── checklists/
│       ├── value-investing-v1.md           # Mode A
│       └── discovery-v1.md                 # Mode B(待写,见 §C8)
├── runs/
│   └── <run_id>/
│       ├── spec.json               # RunSpec(Section 0 + 元数据)
│       ├── events.jsonl            # 完整事件流(append-only)
│       ├── graph.json              # 当前 graph 快照
│       ├── graph_history/          # graph 版本快照
│       └── report.md               # 渲染输出(完成后生成)
└── memory/
    ├── semantic/                   # 跨 run 的语义记忆(实体存)
    └── procedural/                 # 学到的研究套路
```

## C7. 关键设计选择与权衡

| 选择 | V0 决定 | 替代方案 | 为什么 |
|------|---------|----------|--------|
| 适配器 | **仅 CLI** | 同时做 Web UI | 单人 V0 用户(用户本人)CLI 摩擦最低;Web 留 V1 |
| GraphStore | **JSON 文件** | Neo4j / SQLite | V0 不引外部依赖;接口已经抽象,V1 可换 |
| Event 持久化 | **JSONL 永不删** | 滚动日志 | 审计 + replay 需要;空间不是 V0 瓶颈 |
| Checkpoint | **CLI 交互式** | 仅文件标记 | 真正人机协作 vs 单纯日志 |
| 跨 run 实体合并 | **手动**(用户在 CLI 触发) | 自动 | V0 简化;V1 加自动化 |
| 后台 vs 前台 run | **后台进程**(daemon) | 前台阻塞 | 用户可同时跑多 run + 干别的事 |

## C8. 本设计触发的新待办事项

这次设计暴露出几个之前没识别的待办项:

1. **Discovery Checklist v1**(`docs/checklists/discovery-v1.md`) — Mode B 需要类似 Mode A checklist 的执行 spec。当前缺。
2. **Tool 接口规范**(`docs/tools-v0.md`) — 每个工具的输入输出 JSON schema 待写。
3. **Critic Persona prompts**(`docs/critics/`) — Buffett / 做空者 / 审计师 三个 critic 的 prompt 模板。
4. **报告渲染器规范** — 从 graph → markdown 的渲染规则(章节顺序、引用格式)。
5. **预算与成本控制策略** — token / time / cost 三个维度的 budget 触发与降级逻辑。

这些是本设计的**直接产物**,但属于下一轮做的事,不在 B/C 本身范围内。

---

# 共享接口契约(Agent ↔ Middle Layer)

**契约 1**:Agent 与中间层**只通过 Event 通信**。Agent 不直接调用任何"显示给用户"的 API;只发 events,中间层翻译给用户。

**契约 2**:Agent 的所有持久状态**只通过 GraphStore**。Agent 不写其他文件;不缓存到内存(单 run 内除外)。

**契约 3**:人对 Agent 的所有影响**只通过两条路径**:
- (a) `CheckpointGateway`(在 checkpoint 处的批准/拒绝/修改)
- (b) `InjectionChannel`(主动 inject 事实 / 跳过 / 修改 checklist)

**契约 4**:Tool 调用**经中间层代理**(Middle Layer → Tool Sandbox),不让 Agent 直连外部。这是 P1 隔离的实质落地。

---

# 等用户决策的开放问题

| # | 问题 | 我建议的默认 | 为什么需要你确认 |
|---|------|--------------|------------------|
| 1 | 后端进程模型 | 前台 + nohup / launchd 后台(简单) | 影响实现复杂度 |
| 2 | 工具实现语言 | Python(假设技术栈 = Python) | 等你 §13 q4 回答 |
| 3 | Agent ↔ Middle Layer 进程间通信 | 单进程内函数调用(V0 简化) | V1 拆服务前先单进程 |
| 4 | Tool sandbox 实现 | subprocess + timeout(简单)/ Vercel Sandbox(隔离更强) | 影响安全性 vs 复杂度 |
| 5 | LLM provider | Anthropic Claude(默认 Opus / Sonnet) | 影响 prompt 风格、cost 模型 |
| 6 | Critic 是否单独模型 | 同模型不同 prompt(V0) | 简单;后续可优化 |
