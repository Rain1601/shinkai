---
name: discovery-v1
mode: mode_b_narrative
version: 1
last_updated: 2026-05-27
total_items: 16
required_items: 13
estimated_runtime_minutes: 40-90 (不含下游 Mode A subruns)
description: Theme-driven discovery checklist for shinkai Mode B. Walks a theme's dependency graph, applies Q1 (quality) and Q2 (underwater) filters, surfaces 3-5 candidates, then orchestrates Mode A deep-dives.
---

# Mode B · Discovery Checklist v1

Used by shinkai's Mode B (叙事发现) to scan a user-chosen theme and surface 3-5 underwater high-quality US-listed candidates. Each surviving candidate auto-triggers a Mode A deep-dive (see `value-investing-v1.md`).

**Mode B 的工作不是深度分析。它是一个带正确过滤器的智能 scanner。深度活归 Mode A。**

## Section 0 · Scoping (用户启动前必填)

| Item | 字段 | Default | Req |
|------|-----|---------|-----|
| 0.1 | 主题名称 + 一句话定义 | — | required |
| 0.2 | 数据 cutoff 日期 | today | required |
| 0.3 | 目标候选数 N | 5 | required |
| 0.4 | BFS 深度 | 3 | required |
| 0.5 | 预算上限(token / time / cost) | — | required |
| 0.6 | 排除清单(已知不感兴趣公司或子领域) | empty | optional |

---

## Section 1 · Theme Understanding (主题理解)

### 1.1 核心价值链描述
- **Why**: Agent 必须理解"钱从哪流到哪",才能正确建图
- **Where**: 行业报告、卖方综合、Wikipedia summary
- **Output**: 1 Theme Entity node + 1 long-form Claim
- **Done when**: 3-5 句话讲清价值链上下游 + 关键节点
- **Req**: required

### 1.2 关键 demand drivers
- **Why**: 找"钱从哪来",判断哪些 layer 受益
- **Output**: 2-4 Claims
- **Done when**: top 3 需求驱动源(谁在花钱 / 为什么)
- **Req**: required

### 1.3 主题时间窗口与生命周期阶段
- **Why**: 新生主题和成熟主题策略不同
- **Output**: Claim
- **Done when**: 阶段判断 + 关键时间节点
- **Req**: required

---

## Section 2 · Dependency Graph Construction (依赖图谱构建)

### 2.1 第一层 · 主流 / 共识公司
- **Why**: 必须先识别明面玩家,才能定义"排除"
- **Where**: 主题 ETF 重仓(NVDX / AIQ / BOTZ / ROBO 等)、卖方综合
- **Output**: 5-15 Entity nodes + `participates_in` edges,标注 `attention_score=high`
- **Done when**: 全部 layer-1 玩家入图
- **Req**: required
- **Note**: 这是 uteki 域,Mode B 不研究它们;但需要在图里以排除候选用

### 2.2 第二层 · 主流的直接邻居
- **Why**: 二层是水下区域的入口
- **Where**: layer-1 公司的 10-K(Customers / Suppliers / Competitors)、卖方供应链报告
- **Output**: Entity nodes + structural edges(supplied_by / sells_to / partnered_with)
- **Done when**: 每个 layer-1 公司至少识别 3 个直接邻居
- **Req**: required

### 2.3 第三层 · 更深一跳的玩家
- **Why**: **V0 头牌捞鱼区** — 水下鱼大多在这一层及更深
- **Where**: layer-2 的 10-K、行业垂直媒体、利基行业研究
- **Output**: Entity nodes + edges
- **Done when**: 选 5-10 个有代表性的 layer-2 公司,各扩展 2-5 个 layer-3 邻居
- **Req**: required

---

## Section 3 · Candidate Pool

### 3.1 候选池整合
- **Why**: layer-1 排除(uteki 域),layer-2/3 = 候选源
- **Output**: 候选 Entity 集合,标注 `layer` + 距离 layer-1 的最短路径
- **Done when**: 50-100 家候选,标注齐全
- **Req**: required

---

## Section 4 · Q1 Quality Filter (高质量过滤) ⚠️ Mode B 最重的一步

### 4.1 对候选池逐家应用 Q1 三层过滤器
- **Why**: 排除质量不过关的"水下垃圾股"(水下 ≠ 高质量)
- **Where**: SEC EDGAR(10-K / 10-Q 取 ROIC / GM / Net Debt / FCF)+ proxy(资本配置)+ 卖方一致
- **Output**: 每家一组 Claims(L1 硬门槛 + L2 护城河打分 + L3 资本配置打分)+ 通过/淘汰标记
- **Done when**: 全候选池跑完;通过家数 typically 10-30(从 50-100)
- **Note**: 可能消耗 Mode B 预算的 40-60%。可以并行化(每家独立);可以用更便宜模型(DeepSeek-V3)做 L1 硬门槛,只在 L2/L3 用 Claude
- **Req**: required

---

## Section 5 · Q2 Underwater Filter (水下过滤)

### 5.1 对 Q1 通过候选应用 Q2
- **Why**: 留下"高质量且确实水下"的最终入围
- **Where**: 卖方覆盖数(FactSet / 公开聚合)、ETF 重仓数据、媒体提及(Google News / 新闻 API)、市值
- **Output**: 每家一组 Claims(各 underwater 信号得分)+ 综合 `underwater_score`
- **Done when**: Q1 通过候选全跑完;按 underwater_score 排序;留 top N×2(默认 10 家)进入人审
- **Req**: required

---

## Section 6 · Manual Triage(强制 checkpoint)

### 6.1 人审最终候选
- **Why**: 自动过滤有边界 case 和噪声;人最后把关
- **Output**: 人确认 / 增删的最终入围名单
- **Done when**: 用户在 N 家(默认 5)上签字;可手动加入"必须深研"的特殊关注
- **Note**: **强制 checkpoint,不可跳过**
- **Req**: required

---

## Section 7 · Mode A Subrun Orchestration

### 7.1 触发 Mode A subrun
- **For each finalist**: spawn 一个 child Run(`mode_a_company`, `anchor = 该 Entity`)
- **Output**: N child run IDs + parent run 记录依赖
- **Done when**: 全部 subrun spawned
- **Req**: required

### 7.2 等待 subrun 聚合
- **Why**: 综合发现报告依赖每家 Mode A 的产出
- **Output**: 等所有 child Mode A 完成(或部分,按用户配置允许部分超时降级)
- **Done when**: 所有 subrun 状态 ∈ {completed, inconclusive, failed}
- **Req**: required

---

## Section 8 · Discovery Report Synthesis(综合发现报告)

### 8.1 综合发现报告草稿
- **Why**: Mode B 对人交付的核心文档
- **Output**: Markdown(从 graph 渲染)+ JSON(机器可读)
- **Done when**: 报告涵盖:为什么是这 N 家、各家 Mode A 主要结论摘要、推荐 watch / buy / pass 标注
- **Req**: required

### 8.2 候选 ranking
- **Why**: N 家里也有优劣序
- **Output**: 1 Claim(综合排序 + 理由)
- **Done when**: 排名 + 关键差异化论证
- **Req**: required

### 8.3 跟踪建议(watch list)
- **Why**: 不入选的也可能值得持续关注
- **Output**: 1 Claim(watch list + 各自触发再 deep-dive 的条件)
- **Done when**: watch list 完整
- **Req**: required

---

## Appendix · 与 Mode A 的接口

- **Section 6 通过的每家公司** → spawn 1 Mode A run(`anchor_node_id = 该 Entity`)
- Mode A 跑完后,其产出的 Thesis 节点 + 完整图谱**回写**到 Mode B 的 graph(通过 `external_ids` 合并 Entity)
- Mode B 的 §8 报告 = 综合每个子 Mode A 的 Thesis + 自己的 Q1/Q2 评分

## Appendix · 与评测的接口

| 评测层 | 在 Mode B 中检查什么 |
|--------|---------------------|
| **L1 事实** | 每个 Evidence 的 source 可访问 + excerpt 真存在(同 Mode A) |
| **L2 同行评审** | Section 5 完成后触发 critic,质疑:"是不是错过重要候选?水下分数是不是计算偏了?" |
| **L3 预测验证** | N 个月后回看:入选 N 家 vs 被排除的对照组,实际表现 |
| **L4 真实回报** | 聚合到主题层面(整篮子的 alpha) |

## 留待 v2

- §4.1 的批处理优化(并行 / 缓存 / 模型分层路由)
- 主题"自动发现"(Agent 自己识别 emerging themes;V0 暂由用户提)
- 跨 theme 候选去重
- "反向反思":每次发现完成后,人工标注"这次错过了什么",形成 supervised 信号
