---
name: value-investing-v1
mode: mode_a_company
version: 1
last_updated: 2026-05-27
total_items: 43
required_items: 32
estimated_runtime_minutes: 60-120
description: Buffett/Munger-school deep-dive checklist for evaluating a US-listed company as a long-term value investment. Drives shinkai Mode A.
---

# Mode A · Value-Investing Checklist v1

Used by shinkai's Mode A (单公司深研). For each company surfaced by Mode B (or selected directly by the user), the Agent executes this checklist against SEC filings, sell-side research, earnings transcripts, and primary research the tools can access. Outputs accumulate as nodes/edges in the company's research graph.

## How to read each item

| Field | Meaning |
|-------|---------|
| **Why** | Justification — Agent uses to judge "did I really answer it" |
| **Where** | Primary data sources — Agent prioritizes these |
| **Output** | Which graph node types this item produces |
| **Done when** | Explicit completion criterion |
| **Req** | `required` (must do) or `optional` (skip if budget tight) |

---

## Section 0 · Scoping (用户启动前必填)

> This section is filled by the human before kickoff. It defines the run's boundary (Q2 design).

| Item | Field | Req |
|------|-------|-----|
| 0.1 | 目标公司 `{ticker, canonical_name}` | required |
| 0.2 | 时间锚定 (截至日期,默认 today) | required |
| 0.3 | 深度档位:`shallow` / `standard` / `deep` | required |
| 0.4 | 已知约束(用户已知事实,Agent 跳过) | optional |
| 0.5 | 加权偏好(特别在意的风险/质量维度) | optional |
| 0.6 | 是否允许 Agent 联网 | required |
| 0.7 | 预算上限(token / time / cost) | required |

---

## Section 1 · Business Understanding (业务理解)

### 1.1 一句话业务描述
- **Why**: 讲不清 = 没理解,后续分析全是空中楼阁。Munger: 一句话不能解释 = 不懂。
- **Where**: 10-K Item 1 (Business), IR 页面, 历年 CEO Annual Letter
- **Output**: 1 Claim
- **Done when**: Claim confidence > 0.8 且能解释主要收入来源
- **Req**: required

### 1.2 收入按业务线/地理拆分
- **Why**: 不同业务线护城河不同,要分开评估
- **Where**: 10-K segment reporting, 10-Q
- **Output**: N Claims + N Evidence
- **Done when**: 每个 segment 占比 + 增长率 + 毛利率均有 evidence
- **Req**: required

### 1.3 客户画像与集中度
- **Why**: 客户集中度是隐藏风险;客户质量决定收入质量
- **Where**: 10-K Risk Factors + Customer Concentration disclosure, 投资者宣讲
- **Output**: Claims + Evidence + Entity nodes (key customers)
- **Done when**: 前 5 客户占比 / 类型识别完毕(或明确"无重大集中")
- **Req**: required

### 1.4 销售模式与渠道
- **Why**: 直销 vs 经销 vs 长协影响利润率和可见度
- **Where**: 10-K MD&A, 历年财报
- **Output**: Claim
- **Done when**: 销售模式分类清晰
- **Req**: required

### 1.5 Recurring vs One-time 收入占比
- **Why**: Recurring 收入估值倍数应更高,影响 valuation 章
- **Where**: 财报、CFO 评论、Investor Day
- **Output**: Claim
- **Done when**: 比例有数字(或明确"无法量化"+原因)
- **Req**: required

---

## Section 2 · Industry & Market (行业与市场)

### 2.1 行业 TAM 与 5/10 年展望
- **Where**: 行业报告 (Gartner / IDC / 公司自述)、卖方行研
- **Output**: Claim + Evidence
- **Done when**: 当前 TAM 数字 + 5 年 CAGR 预测 + 来源
- **Req**: required

### 2.2 行业生命周期与周期位置
- **Why**: AI infra 表面长牛,底下仍周期 — 不能忽视
- **Output**: Claim
- **Done when**: 阶段定位 + 当前在周期哪里 + 论证
- **Req**: required

### 2.3 关键驱动因素
- **Why**: 技术 / 监管 / 需求循环,各自演化路径不同
- **Output**: 2-4 Claim
- **Done when**: 列出 top 3 驱动因素 + 每个的方向性判断
- **Req**: required

### 2.4 公司细分定位
- **Why**: top-3? niche leader? challenger? 决定竞争策略
- **Output**: Claim + Edges to competitors (Entity nodes)
- **Done when**: 市场份额 + 主要竞争对手 + 相对定位
- **Req**: required

### 2.5 国际同行类比
- **Why**: 类比能加速判断(尤其新行业)
- **Output**: Claim + Entity edges
- **Done when**: 找到 1-2 个国际可比公司,简述差异
- **Req**: optional

---

## Section 3 · Moat (竞争优势 / 护城河)

### 3.1 护城河类型识别
- **Why**: 类型决定持续性。无护城河 = 普通生意 = 不是 shinkai 的目标
- **Where**: 综合分析
- **Output**: Claim(每个类型一条)
- **Done when**: 至少一个类型 + 论证;若无,显式 Claim "无护城河"(直接降低 conviction)
- **Req**: required

### 3.2 Porter 五力分析
- **Output**: 5 Claims
- **Done when**: 每力都有判断 + 论证
- **Req**: required

### 3.3 历史 ROIC 与毛利率趋势 — 护城河信号
- **Why**: 真护城河会反映在 ROIC 持续高于资本成本 + 毛利率不被竞争侵蚀
- **Where**: 10 年财务数据
- **Output**: Claim + Evidence (时间序列)
- **Done when**: 10 年趋势图 + 解读
- **Req**: required

### 3.4 客户切换成本量化
- **Why**: 切换成本是最隐蔽但最强的护城河
- **Output**: Claim
- **Done when**: 估算客户切换的金钱/时间/风险代价(可定性,带 confidence)
- **Req**: required

### 3.5 关键 IP / 技术 / 许可
- **Where**: 10-K Intellectual Property, 专利数据库
- **Output**: Claims + Evidence
- **Done when**: 关键专利/许可/技术列表 + 到期日(若适用)
- **Req**: required

### 3.6 终局思考:10 年后这门生意还在吗?
- **Why**: 长期投资必答题。Bezos: "What won't change in 10 years?"
- **Output**: Claim (long-horizon)
- **Done when**: 10 年后业务是否存在 + 形态如何变 + 关键不变量
- **Req**: required

---

## Section 4 · Financial Quality (财务质量)

### 4.1 10 年关键财务表现回顾
- **Where**: 10-K 历年, Stockanalysis.com / Macrotrends
- **Output**: 1 Evidence (大表) + 多个 Claim 描述趋势
- **Done when**: Revenue / EBIT / FCF / ROIC / GM / NM 十年表完整
- **Req**: required

### 4.2 FCF 转化率与稳定性
- **Why**: 利润可以包装,FCF 包装难度大
- **Output**: Claim + Evidence
- **Done when**: FCF/NI 比率 5-10 年趋势
- **Req**: required

### 4.3 Capex 拆分:maintenance vs growth
- **Why**: 真自由现金流 = Operating CF - maintenance capex(不是 total capex)
- **Where**: MD&A, Q&A on calls
- **Output**: Claim
- **Done when**: 比例估算(可定性)
- **Req**: required

### 4.4 营运资本周转趋势
- **Why**: 应收账款 / 库存恶化常是早期红旗
- **Output**: Claim
- **Done when**: DSO / DIO / DPO 趋势 + 异常解释
- **Req**: required

### 4.5 资产负债表健康度
- **Output**: Claims + Evidence
- **Done when**: 净债务 / EBITDA, 利息保障倍数, 现金 / 短债, 流动比率 均有数
- **Req**: required

### 4.6 会计政策与红旗信号
- **Why**: revenue recognition / inventory / R&D 资本化 是常见雷
- **Where**: 10-K 附注、Auditor's Report
- **Output**: Claim (per concern) 或 "未发现红旗"
- **Done when**: 关键政策审查 + 明确判断
- **Req**: required

### 4.7 Off-balance-sheet 项目
- **Where**: 10-K 附注 Commitments & Contingencies
- **Output**: Claim
- **Done when**: 列出 + 评估实质风险
- **Req**: optional

---

## Section 5 · Management & Capital Allocation (管理层与资本配置)

### 5.1 CEO/CFO 背景、任期、过往业绩
- **Where**: Proxy DEF 14A, LinkedIn, 历史新闻
- **Output**: Entity nodes (Person) + Claims
- **Done when**: 关键高管 profile + 过往业绩评估
- **Req**: required

### 5.2 高管薪酬结构与股东对齐度
- **Why**: 薪酬看股东是否真和管理层一条船
- **Where**: DEF 14A (Compensation Discussion)
- **Output**: Claim
- **Done when**: 短期 vs 长期、与 EPS / 总回报 / ROIC 挂钩程度 评估
- **Req**: required

### 5.3 内部人持股 + 近期交易
- **Where**: Form 4, SC 13G/D, OpenInsider
- **Output**: Claim + Evidence
- **Done when**: 内部人持股比例 + 过去 12 月净买/净卖 + 解读
- **Req**: required

### 5.4 历史资本配置评估
- **Why**: Buffett: "CEOs are largely judged by their capital allocation decisions"
- **Output**: Multiple Claims
- **Done when**: 三方面全有评估:
  - **5.4a** 重大 M&A:时点、估值、整合 ROI
  - **5.4b** 回购:历年价格 vs 当时内在价值
  - **5.4c** 分红 vs 再投资 纪律
- **Req**: required

### 5.5 历年指引兑现率 + 沟通诚实度
- **Why**: 长期诚实是稀缺品。糟糕季度怎么沟通 比 好季度怎么吹 更说明问题
- **Where**: 历年 earnings call transcripts
- **Output**: Claim
- **Done when**: 3-5 年指引 vs 实际偏差 + 坏消息披露时机评估
- **Req**: required

### 5.6 关键人物风险
- **Output**: Claim
- **Done when**: 是否有 single-point-of-failure 人物风险 + 继任计划
- **Req**: optional

---

## Section 6 · Valuation (估值)

### 6.1 当前估值倍数
- **Output**: Claim + Evidence
- **Done when**: PE / EV-EBIT / EV-FCF / P/S / P/B 全列
- **Req**: required

### 6.2 5-10 年估值带分位
- **Where**: Capital IQ / Stockanalysis.com / 自算
- **Output**: Claim
- **Done when**: 各倍数当前在历史分布的哪一分位 + 解读
- **Req**: required

### 6.3 同行估值对比
- **Output**: Claims + Edges to peers
- **Done when**: 3-5 同行可比 + 解释为何溢价/折价合理或不合理
- **Req**: required

### 6.4 DCF 三档(保守 / 基线 / 乐观)
- **Output**: 3 Claims + 1 Evidence (假设表)
- **Done when**: 每档关键假设(收入增长 / 利润率 / WACC / 终值)透明,内在价值区间
- **Req**: required

### 6.5 隐含市场预期反推
- **Why**: 反推市场预期 → 判断你和市场谁更可能对
- **Output**: Claim
- **Done when**: 当前价格隐含的 5 年收入/利润率假设 + "市场对了还是错了"判断
- **Req**: required

---

## Section 7 · Risk (风险)

### 7.1 商业模式被颠覆的风险
- **Why**: 技术革命可以让最强护城河失效
- **Output**: Claim
- **Done when**: 最具威胁的颠覆路径 + 时间窗 + 公司应对
- **Req**: required

### 7.2 行业 / 周期风险
- **Output**: Claim
- **Done when**: 周期下行情景下的财务韧性测算
- **Req**: required

### 7.3 监管 / 政策 / 地缘
- **Why**: 美股投资中 AI / chip / data 行业都被监管和地缘强烈影响
- **Output**: Claims
- **Done when**: 关键监管/政策/地缘风险列表 + 影响估算
- **Req**: required

### 7.4 客户集中 / 供应链 单点风险
- **Output**: Claims
- **Done when**: 关键 single-point dependencies 识别(连接到图谱中的 Entity)
- **Req**: required

### 7.5 ESG / 治理 / 法律
- **Output**: Claim 或 "未发现重大问题"
- **Done when**: 重大诉讼 / 治理事件 / 环境合规 扫描
- **Req**: optional

---

## Section 8 · Endgame & Thesis (终局与论点)

> **这一节必须最后做。它把前 7 节的产出综合成可投资的 Thesis 节点。**

### 8.1 5 年 / 10 年终局假设
- **Output**: 1-2 Claims (long-horizon, low confidence acceptable)
- **Done when**: 终局图像清晰(变成多大、利润率多少、市场地位、行业格局)
- **Req**: required

### 8.2 核心 Thesis(一句话 + 3-5 个 supporting claim)
- **Output**: **1 Thesis node** with `supporting_claim_refs` 填好
- **Done when**: Thesis statement 一句话能讲清,supporting claims 都已在图谱中
- **Req**: required

### 8.3 Kill Criteria(哪些 Claim 被证伪即推翻 thesis)
- **Why**: 没有 kill criteria 的论点 = 没有评测锚点,违反第 5 原则。
- **Output**: 填 Thesis 节点的 `key_risk_refs`
- **Done when**: 3-5 条"如果发生则我错"的具体可观测信号
- **Req**: required(**绝不可跳**)

### 8.4 Position 建议 + Conviction 评级
- **Output**: 填 Thesis 节点的 `position` + `conviction` + 可选 `target_price`
- **Done when**: 位置(Long / Watch / Avoid / Short)+ Conviction (0-1) 都填好,且 conviction 的论证可追溯到具体 evidence
- **Req**: required

---

## Appendix · 与项目其他设计的接口

### A. 研究图谱节点对应表

| Checklist Output | 图谱节点类型 |
|------------------|--------------|
| 业务/客户/同行/管理层 | Entity (Company / Person / Market) |
| 任何带 confidence 的判断 | Claim |
| 财报数据、文档摘录、新闻引用 | Evidence |
| 未答问题 | Question |
| 8.2 / 8.4 的核心论点 | Thesis(每次研究产出 1 个) |

### B. 评测接口

| 评测层 | 检查什么 |
|--------|----------|
| **L1 事实校验** | 每个 Evidence 的 source_uri 可访问、excerpt 真存在 |
| **L2 同行评审 (Critic)** | Section 8.3 Kill Criteria 是否齐全;高 confidence Claim 是否有 evidence_count ≥ 2;有无 counter_evidence |
| **L3 预测校验** | 6.4 DCF 与 6.5 反推预期,N 个月后回看 |
| **L4 真实回报** | 8.4 的 Position 建议在 N 月/年后的实际表现 |

### C. 用户介入点(Q2 边界设计的具象)

- **启动前**:用户填 Section 0,可调整 required / optional / depth
- **Section 3 完成后**:中间层强制提示用户 review 护城河结论(如果护城河弱,提前止损)
- **Section 6 完成后**:中间层强制提示用户 review 估值(是否处于合理买入区间)
- **Section 8 完成前**:中间层强制人在 Kill Criteria 确认 — 因为这是评测的锚

---

## 留待 v2 演进

- **行业特化 checklist**:AI infra / 消费 / 医药 各自有特殊维度,v2 考虑做 inheritance
- **Mode B 用的 Discovery Checklist**:不同于 Mode A,Discovery 重点在遍历 + 过滤,逻辑会更短
- **检查项依赖图**:某些项有依赖(估值依赖财务、终局依赖护城河),v2 显式建模
- **自适应深度**:Agent 根据中途发现的红旗自动加深某些 section
