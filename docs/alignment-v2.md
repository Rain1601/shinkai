# Shinkai V0 · Alignment v2 — Implementation-Ready Spec

> **时间**:2026-05-27 · **最近实现盘点**:2026-05-31
> **状态**:概念设计 **COMPLETE**。本文档是 V0 实施的权威 spec。
> **前一版**:`docs/alignment-v1.md`(对话式记录,保留作历史参考,**不再权威**)
> **关系**:v1 = "我们怎么走到这一步的对话记录";v2 = "我们决定怎么做的实施规范"

## ⚠ Implementation Status Map(诚信声明)

下表对照 spec 与当前 code(2026-05-31)的差距,避免"看文档以为 X 已建好"的误解。

| Spec 章节/能力 | 状态 | 备注 |
| --- | --- | --- |
| Run 生命周期 + AgentEvent 总线 + SSE | ✅ Built | `runs/`、`schemas/events.py`、`api/runs.py` |
| Mode B 叙事发现(确定性 fallback) | ✅ Built | `agent/harness.py` 走 `AI_SUPPLY_CHAIN_LAYERS` 硬编码清单 |
| Mode B 叙事发现(LLM 真驱动 frontier) | ❌ Not built | DeepSeek 当前只装饰固定 trajectory,**不是真正的发现** |
| Mode A 公司深研 dossier | ⚠ Partial | dossier 字段生成,但 checklist 43 项未完整对照 |
| Research Graph(5 节点 / 4 边) | ✅ Built | `graph/`、`research/`、node id 已改为确定性 hash |
| Mode A 价值投资 checklist v1 | ⚠ Partial | doc 完整但 harness 只实现少数 check |
| 3 级 Agent Loop(Run/Item/Step ReAct) | ❌ Not built | 当前是单层 frontier loop,LLM 不做 ReAct 决策 |
| 中间层:观察(SSE/events) | ✅ Built | 事件可订阅 |
| 中间层:暂停/恢复 | ⚠ Partial | pause 状态存在,但 inject channel 未建 |
| 中间层:checkpoint approval | ❌ Not built | UI affordance 缺失 |
| 中间层:cross-device handoff | ❌ Not built | iOS 客户端未建 |
| 4 层 eval(L1 形态 / L2 critic / L3 预测 / L4 真实回报) | ⚠ L1 only | `eval/runner.py` 是形态/统计检查,L2-L4 未建 |
| 4 层 memory(Working / Episodic / Semantic / Procedural) | ❌ Not built | 仅 per-run state |
| Critic 三 persona(Buffett/short-seller/auditor) | ❌ Not built | spec 描述但无 prompt 与代码 |
| LLMRouter(DeepSeek + Claude via AIHubMix) | ❌ Not built | 当前只 DeepSeek 一条 |
| Postgres-first persistence + JSON fallback | ✅ Built | 投影表写已加事务,fallback 改为 sticky |
| 自我迭代 spiral(child runs) | ✅ Built | `_maybe_spawn_next_spiral` |
| Web 仪表盘(/runs /graph /eval /review /a2a) | ✅ Built | 但偏 status viewer,非 cockpit |
| iOS 原生 SwiftUI | ❌ Not built | 完全没动 |

**主要 leap 还未跨过**:LLM 真正驱动 frontier(把 `AI_SUPPLY_CHAIN_LAYERS` 从权威路径降级为 fallback)。在这之前,"discover underwater companies" 的承诺与 V0 跑出来的实际轨迹之间有显著差距。

---

## 0. TL;DR(只看一段)

shinkai 是一个自主投研 Agent — 在用户选定的主题(如 AI Infrastructure)里**发现被忽视的高质量美股公司**,然后用巴芒派 checklist **深度分析**每一家。产出同时是人类可读报告 + 机器可读研究图谱(可被其他 Agent 复用)。

**绝不可违反的核心承诺**:
1. Agent 在自己的执行环境跑,人通过中间层与之交互(观察/控制/审计)
2. 工具极简(6-10 个)
3. 单 Agent 优先,多 Agent 延后
4. 每个架构决策都要能回答:"这能被观测吗?能被评测吗?"

**V0 首跑**:在 **AI Infrastructure** 主题上跑一次 Mode B 发现 → 浮现 3-5 家水下高质量公司 → 每家自动触发 Mode A 深研。

---

## 1. 使命与定位

shinkai 是一个聚焦**深度投研**的前沿 Agent 应用。具体任务:

> 在用户选定的主题下,**发现被低估 / 被忽视 / 被低关注**的**高质量**美股公司,然后深度分析每一家。

项目名 **深海(shinkai)**取自日语"深海",寓意"深邃、神秘、探索水下"。

### shinkai / uteki 分工

| 项目 | 任务 | 覆盖范围 |
|------|------|---------|
| **uteki**(已有) | 持续追踪明面/共识公司 | NVDA, ASML, GOOG, TSMC, AAPL, MSFT … |
| **shinkai**(本项目) | 在主题内捞水下高质量公司 | 二三线、覆盖少但基本面强的名字 |

两者互补。shinkai 发现的公司"毕业"为共识后,可流入 uteki 的追踪清单。

---

## 2. 五条第一性原则(load-bearing)

V0 所有设计决策必须对齐以下五条。

### P1 · 三层架构:Human ↔ Middle Layer ↔ Agent
Agent 在自己有界的执行环境跑(sandbox / VM / 远程 worker)。中间层提供:**可观测 + 可控制 + 可审计**。人通过中间层交互,不直接被 Agent 接管。

**反模式**:不要把 Agent 放进人的主工作环境(OpenAI Operator / Computer Use 模式)。

### P2 · 工具极简
研究 Agent 的工具数量目标 6-10 个。工具越多 → 模型选择压力非线性上升 → 描述污染上下文 → 组合爆炸 → 出错率上升。优先组合原语,避免特化工具。

### P3 · 执行层 vs 核心层
`brain (model) + tools` 是**执行层**(随时间趋于商品化)。`memory + evaluation + critic + iteration + task-framing` 是**核心层**(护城河所在)。设计资源向核心层倾斜。

### P4 · 单 Agent 优先
多 Agent 现阶段被严重高估,大多数"多 Agent 胜利"实为更好的上下文隔离。先把单 Agent 做深做稳,V0 之后再说多 Agent。

### P5 · 可观测 + 可评测(元原则)
每个架构决策都要能回答:
- **能被观测吗?**(人机交互的基础,无观测则无信任)
- **能被评测吗?**(进化的基础,无测量则迭代盲改)

如果两个问题任何一个答不上,推翻重新设计。

---

## 3. V0 范围

### 双模式,共享一个引擎

| Mode | 角色 | 入口 | 产出 |
|------|------|------|------|
| **Mode B · 叙事发现** ⭐ **V0 头牌** | 发现水下候选 | 一个 Theme(用户选) | 3-5 家浮现公司 + 综合发现报告 |
| **Mode A · 公司深研** | 单公司深度分析 | 一家 Company(通常由 Mode B 自动触发,也可单独跑) | 深度论点(巴芒派) |

**为什么可以同时做**:Mode B 的产出就是"哪些公司要跑 Mode A"。两者是组合关系,不竞争范围。共享同一引擎、同一研究图谱、同一 checklist 机制(不同 checklist)、同一 critic / eval。

**延后到 V1+**:短期催化剂 / 事件驱动研究。方法论不同,V0 同时做会分散火力。

### V0 首跑试点配置(已锁定)

| | 取值 |
|---|---|
| Theme | **AI Infrastructure** |
| 市场 | 仅美股 |
| 产出目标 | 3-5 家浮现公司 + 每家 Mode A 深研 |

---

## 4. 两个操作过滤器(Q1 / Q2)

Mode B 从主题的依赖图谱中拉到候选后,串行应用两个过滤器。

### Q1 · 高质量过滤器(AI infra v0 默认值)

**Layer 1 · 硬性定量门槛(必须全过)**:

| 指标 | 阈值 |
|------|------|
| 3 年平均 ROIC | > 12% |
| 毛利率 | > 25% |
| Net Debt / EBITDA | < 3x |
| FCF(滚动 4 季度) | > 0 |

**Layer 2 · 定性护城河(Agent 打分)**:
- 类型:技术 / 切换成本 / 规模 / 网络效应 / 品牌(≥ 1)
- 持续性:5+ 年高把握 / 不确定
- 趋势:扩宽 / 稳定 / 侵蚀

**Layer 3 · 资本配置评级(Agent 从 proxy + 财报 + 电话会评估)**:
- 回购:低估买回 vs 高位接盘
- M&A:历史 ROI
- 分红 vs 再投资:纪律

### Q2 · 水下过滤器(AI infra v0 默认值)

**关键 reframe**:"水下"= **质量与关注度严重不匹配** — $5B 市值、ROIC 20% 但只有 6 个卖方覆盖的公司,就是水下。

| 信号 | V0 默认 |
|------|--------|
| 市值带 | $500M – $10B |
| 卖方覆盖 | < 10 家 |
| ETF 排除 | 不在 NVDX / AIQ / BOTZ / ROBO 的前 30 重仓 |
| 依赖图谱深度 | ≥ 2 跳(距 NVDA / hyperscalers) |
| 媒体冷度 | 主流财经媒体近 90 天提及 < 阈值(V0 用相对分位) |
| 加分信号 | 卖方一致 Hold/Sell + 财务质量改善 |

候选必须 **同时通过 Q1 与 Q2** 才进入 Mode A。

---

## 5. 研究图谱(数据模型)

完整 schema:`docs/research-graph-schema-v0.md`。这里给摘要。

### 为什么用图谱而非 Markdown 报告

Markdown 报告是**渲染视图**,图谱是事实之源。原因:
- 局部更新(新信息无需重写全文)
- 跨研究复用(研究 A 时建的 `TSMC supplies NVDA` 边,研究 B 时直接复用)
- Critic 友好(直接遍历低 confidence claims)
- 自动失效传播(被推翻的 evidence 自动标红依赖它的 thesis)
- 机器可消费(其他 Agent 直接读)

### 5 种节点

| 类型 | 含义 |
|------|------|
| **Entity** | 实体(Company / Person / Product / Market / Theme / Geography / Event) |
| **Claim** | 断言(带 confidence、evidence_refs、counter_evidence_refs) |
| **Evidence** | 证据/数据点(excerpt、source_uri、reliability) |
| **Question** | 开放问题(驱动进一步研究) |
| **Thesis** | 综合投资观点(position、conviction、kill_criteria) |

### 4 种边

| 类型 | 例子 |
|------|------|
| **Structural** | supplied_by, supplies_to, competes_with, owns, participates_in |
| **Evidential** | supports, contradicts, qualifies, weakens |
| **Logical** | implies, depends_on, decomposes_into |
| **Temporal** | precedes, triggers, expires_at, valid_during |

### 所有节点/边的强制元数据

`id`, `created_at`, `created_by`, `confidence`, `decay.half_life_days`, `tags`。每个断言(包括结构性边)本身都是可证伪的 — 所以边也有 confidence。

---

## 6. Mode A · 公司深研 Checklist(摘要)

完整版:`docs/checklists/value-investing-v1.md`。43 项 / 32 必做 / 8 节。

### 8 节

| # | 章节 | 项数 | 备注 |
|---|------|------|------|
| 0 | Scoping | 7 | **用户启动前填写(Q2 边界入口)** |
| 1 | 业务理解 | 5 | |
| 2 | 行业与市场 | 5 | |
| 3 | 护城河 | 6 | 强制人机 review 点 ① |
| 4 | 财务质量 | 7 | |
| 5 | 管理层与资本配置 | 6 | |
| 6 | 估值 | 5 | 强制人机 review 点 ② |
| 7 | 风险 | 5 | |
| 8 | 终局与论点 | 4 | **必须最后做;8.3 Kill Criteria 不可跳** |

### 三个强制人机交互点(对应 P5 + Q2)

1. **Section 3 后**(护城河结论)— 弱护城河直接止损
2. **Section 6 后**(估值)— 是否处于合理买入区间
3. **8.3 处**(Kill Criteria)— 人确认评测锚点

### 单公司预估执行成本

60-120 分钟 wall clock(取决于工具延迟、深度档位 `shallow`/`standard`/`deep`、critic 轮次)。

---

## 7. Mode B · 叙事发现工作流

```
用户选 Theme(如 "AI Infrastructure")
   ↓
Agent 遍历 Theme 的依赖图谱(BFS,~3 层深度)
   ↓
候选(50-100 家)从图谱第 2-3 层收集
   (第 1 层 = 主流共识,通常排除 — uteki 域)
   ↓
应用 Q1(质量)过滤 → 留下 ~10-30 家
   ↓
应用 Q2(水下)过滤 → 留下 ~3-10 家
   ↓
每家自动触发 Mode A 深研
   ↓
产出:
  · 综合发现报告(为什么是这 N 家)
  · 每家深度公司报告 + 研究图谱
   ↓
用户判断:这些发现是不是真的"水下高质量"?
   ↓
反馈进 L2 评测 → 调 Q1/Q2 阈值 / 改 prompt
```

### Mode B 相比 Mode A 多一个 Agent 工具

`theme_dependency_traversal` — 给定 Theme 节点,扩展其 `participates_in` / `supplied_by` / `serves_market` 子图至 N 跳。其他工具与 Mode A 共享。

---

## 8. 四层评测架构

直接回应用户 Q2(评测以真实表现构建)。北极星是真实表现,但日常迭代需要更快的代理信号。

| 层 | 反馈周期 | 检查什么 | 用于迭代什么 |
|---|----------|----------|--------------|
| **L1 · 事实/引用** | 秒 | 每个 Evidence 的 source_uri 可访问、excerpt 真存在 | 自动拦截幻觉 |
| **L2 · 同行评审** | 小时 | Critic Agent / 人工:kill criteria 是否齐全;高 conf claim 是否 evidence 不足;反证据是否存在 | prompt / 流程迭代 |
| **L3 · 预测准确率** | 周-月 | checklist 中可验证的预测(DCF, 6.5 反推预期, 8.1 终局)在时点 N 的兑现 | 方法论迭代 |
| **L4 · 真实回报** | 月-年 | Mode A thesis 的 position 在 horizon 内 vs benchmark | 世界观迭代(北极星) |

L4 是终极真值,但 L1-L3 是迭代回路。没有 L1-L3,L4 永远不会收敛。

### 用 Backtest 加速 L3/L4(长期投资专属便利)

Mode A 可以做:"如果 2020 年用 shinkai 在 2020 年数据上研究公司 X,论点会是什么?2024 年回看对不对?"这把 L4 的反馈周期压缩到 backtest 速度。

---

## 9. 记忆系统设计

v1 提过未细化。v2 锁定四层:

| 层 | 范围 | 存储 | 衰减 |
|---|------|------|------|
| **Working** | 当前任务上下文 | LLM context window | N/A(瞬时) |
| **Episodic** | 过去研究跑("做过什么、得出什么") | 单次 graph + run 元数据 | 无 — 历史 artifact |
| **Semantic** | 稳定学到的事实("Apple 由 TSMC 供货", "SK Hynix HBM 第一") | 跨图谱实体存,按 external_id 索引 | 时间感知,通过 decay.half_life_days |
| **Procedural** | 学到的研究套路("消费股先看品牌护城河") | 模板化为 checklist 变体 + prompt 模板 | 仅人工或显式 Agent 学习更新 |

**Consolidation**(episodic → semantic)是最难的问题,也是与朴素 RAG 的区分点。V0 采用简单做法:**每次 Mode A 跑完,LLM 生成 "本次学到什么" 摘要,作为候选 semantic 记忆;人工 reviewer 批准入库**。自动化延后到 V1+。

---

## 10. Critic / Self-Play / Replay 设计

按 P3(核心层是护城河),这些是一等公民:

### Critic Agent
- V0:同模型不同 prompt
- 人格变体:"Buffett critic"(找护城河弱点)、"做空者 critic"(找隐藏风险)、"审计师 critic"(找会计红旗)
- 运行时点:Section 3 后、Section 6 后、8.3 处(与强制 review 点对齐)

### Bull/Bear Self-Play
- 8.2(Thesis 陈述)后,Agent 生成最强反方案例
- 产出:counter-thesis + counter-claims + counter-evidence
- 不一致强制解决 → 强化或弱化 conviction

### Replay
- 相同 Section-0 scoping、相同数据截止、多次 Agent 跑
- 分歧 = 不确定性表面
- 记入 Thesis 的 `replay_variance`(可扩展字段)— 高方差 = 低 confidence,不论单次 conviction

---

## 11. 架构:Human ↔ Middle Layer ↔ Agent

### 组件图

```
┌───────────┐       ┌────────────────────┐       ┌─────────────────────┐
│   Human   │ <───> │   Middle Layer     │ <───> │  Agent Execution    │
│ (analyst) │       │  (observe / steer  │       │  Environment        │
└───────────┘       │   / review / audit)│       │  (sandbox / VM)     │
                    └────────────────────┘       └─────────────────────┘
                            │                              │
                            ▼                              ▼
                    ┌────────────────┐            ┌────────────────┐
                    │  Research      │            │  Tools         │
                    │  Graph Store   │ <───────── │  (web_search,  │
                    │  (事实之源,    │            │   web_extract, │
                    │   可版本化)     │            │   filings, …)  │
                    └────────────────┘            └────────────────┘
```

### 中间层职责

- **Observe**:意图链、置信度轨迹、资源消耗、可介入点
- **Steer**:暂停 / 恢复 / 注入信息 / 跑中修改 checklist
- **Review**:三个强制 review 点(S3 后、S6 后、8.3 处)
- **Audit**:全历史 who-did-what;可复现

### Agent 执行环境

- 跑 Agent 主循环(checklist → tool calls → graph writes → critic 检查 → 迭代)
- 有界:工具表面、网络访问、预算
- 无状态(除 Research Graph Store 外,该 store 持久、可观测、版本化)

### 中间层形态(V0 最小)

待决策。选项:
- CLI(最快搭、单用户摩擦最低)
- Web UI(最终 B2B/B2C 必要;可 V1)
- API + 薄查看器(中间路线)

待用户给出部署目标后决定。

---

## 12. 输出形态(双面向)

按用户 Q1 决策:输出同时服务人 + 其他 Agent。

| 受众 | 形态 |
|------|------|
| 人 | 渲染的 Markdown 报告(从图谱生成)— 章节与 checklist 对齐 |
| 其他 Agent | JSON 序列化的 ResearchGraph(按 schema v0) |
| 跨研究消费 | 按 external_id 索引的实体存储,可按 ticker / theme / 事实类型查询 |

**推论**:报告中不能有图谱里不存在的内容。报告是视图;视图说了图谱没说的,视图就是错的。

---

## 13. 开放的实施问题

注意:这些**不是**概念问题(概念已锁)。是等待用户输入的实施选择。

| # | 问题 | 影响 | 如不答的默认值 |
|---|------|------|--------------|
| 1 | 用户提到的另一个项目 | 校准 Mode B UX;明确 shinkai/uteki 接口 | 不等,看到再融入 |
| 2 | SEC EDGAR 之外的主要数据源 | 工具实现 | EDGAR + 免费 FMP + Yahoo Finance + Tavily(web 搜索) |
| 3 | 部署目标(SaaS / 自托管 / 混合) | 中间层形态 | CLI + 本地文件存储(V0) |
| 4 | 技术栈(Python vs TS) | 代码库 | Python(PyCharm 信号 + Agent 生态成熟) |
| 5 | 团队与时间线 | 范围合理性 | 单人 + 数周到首 MVP |
| 6 | LLM API 预算量级 | critic / replay 频率 | 保守:V0 单 critic pass,不做 replay |

---

## 14. 延后到 V1+

- Mode C:短期催化剂 / 事件驱动研究
- 自动 consolidation(episodic → semantic)
- 真正多 Agent 协作(超出 critic / self-play 范围)
- 行业特化 checklist 变体(AI infra v1 → 消费 v1 → biotech v1 …)
- 实时 backtest 基础设施
- 跨研究实体合并自动化
- 生产级中间层(Web UI、RBAC、审计日志导出)
- 向量 DB 或图数据库后端(V0 用 JSON 文件)

---

## 附录 · 文档地图

| 文档 | 用途 | 状态 |
|------|------|------|
| `docs/alignment-v1.md` | 概念对齐阶段的对话式记录 | Historical |
| `docs/alignment-v2.md`(本文档) | 实施权威 spec | **Authoritative** |
| `docs/research-graph-schema-v0.md` | 数据模型(TypeScript + JSON 实例) | Authoritative |
| `docs/checklists/value-investing-v1.md` | Mode A 深研 checklist | Authoritative |
| `memory/MEMORY.md`(Claude 项目记忆) | 决策记忆文件索引 | Maintained |

---

## 结尾 · 本文档的作用与不作用

**作用**:锁定 V0 概念设计。后续任何功能决策都应该对照本文档,要么契合,要么显式修订本文档。

**不作用**:不决定技术栈、数据源、部署、代码结构等实施细节。那是下一阶段。

下一步:Agent 主循环设计(B)、中间层最小形态(C),然后技术栈决定,然后开始写代码。
