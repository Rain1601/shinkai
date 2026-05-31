# Shinkai Research Graph Schema v0

> **状态**:概念设计版,核心 Source/Evidence/Claim/Candidate/Task 域模型已实现
> **时间**:2026-05-27
> **配套文档**:`docs/alignment-v1.md`

研究图谱是 shinkai 的"机器可读骨架"。所有 Agent 产出最终都落到这个结构上;
Markdown 报告是从图谱**渲染**出来的视图。

## 设计原则(对应 alignment-v1 的五条第一性原则)

- **可观测/可评测**:每个节点/边都有 `confidence` 和 `source`,任意时刻可被 critic 检查
- **跨研究复用**:`Entity.external_ids` 让"苹果"在所有研究里能 merge
- **时间感知**:`decay.half_life_days` 表达事实的渐进衰减(投研刚需)
- **支持 critic / self-play**:`counter_evidence_refs` 显式独立,让反方证据触手可得
- **Mode A & Mode B 共享底层**:`mode` 在图谱级,Entity 可跨图引用

## TypeScript Schema(可直接序列化为 JSON)

```typescript
// === 基础标识 ===
type NodeId   = string;
type EdgeId   = string;
type AuthorId = string;            // "agent:shinkai-researcher-v1" 或 "human:user"
type ISODate  = string;            // ISO 8601

// === 公共节点元数据 ===
interface NodeMeta {
  id: NodeId;
  type: "Entity" | "Claim" | "Evidence" | "Question" | "Thesis";
  created_at: ISODate;
  created_by: AuthorId;
  updated_at: ISODate;
  last_verified_at?: ISODate;
  confidence: number;              // 0-1
  decay: {
    half_life_days: number;        // 0 = 永不衰减(历史事实)
    expires_at?: ISODate;
  };
  tags: string[];
  notes?: string;
}

// === 五种节点 ===

interface EntityNode extends NodeMeta {
  type: "Entity";
  entity_kind: "Company" | "Person" | "Product" | "Market" | "Theme" | "Geography" | "Event";
  canonical_name: string;
  aliases: string[];
  external_ids?: {
    ticker?: string;
    isin?: string;
    cik?: string;
    wikidata?: string;
    [key: string]: string | undefined;
  };
  attributes?: Record<string, unknown>;
}

interface ClaimNode extends NodeMeta {
  type: "Claim";
  statement: string;
  claim_kind: "Quantitative" | "Qualitative" | "Forward" | "Historical";
  verification: "support" | "refute" | "insufficient" | "stale";
  temporal_scope?: { from?: ISODate; to?: ISODate };
  subject_refs: NodeId[];
  evidence_refs: NodeId[];
  counter_evidence_refs: NodeId[];
}

interface EvidenceNode extends NodeMeta {
  type: "Evidence";
  source_kind: "FinancialReport" | "Filing" | "News" | "Transcript"
             | "PrimaryResearch" | "Computed" | "AgentInference" | "Other";
  source_tier: "primary" | "secondary" | "tertiary" | "agent_inference";
  source_uri?: string;
  source_locator?: string;
  citation_anchor?: string;
  excerpt: string;                 // 原文摘录,防失链
  retrieved_at: ISODate;
  reliability: 1 | 2 | 3 | 4 | 5;
}

interface QuestionNode extends NodeMeta {
  type: "Question";
  question_text: string;
  priority: "high" | "medium" | "low";
  status: "open" | "investigating" | "answered" | "dropped";
  answer_claim_ref?: NodeId;
}

interface ThesisNode extends NodeMeta {
  type: "Thesis";
  statement: string;
  position: "long" | "short" | "watchlist" | "avoid" | "neutral";
  time_horizon: "short" | "medium" | "long";
  subject_refs: NodeId[];
  supporting_claim_refs: NodeId[];
  key_risk_refs: NodeId[];
  conviction: number;
  target_price?: number;
  as_of: ISODate;
}

type Node = EntityNode | ClaimNode | EvidenceNode | QuestionNode | ThesisNode;

// === 边 ===

type StructuralRelation =
  | "supplied_by" | "supplies_to" | "competes_with"
  | "owns" | "owned_by" | "subsidiary_of"
  | "participates_in" | "serves_market"
  | "managed_by" | "manages"
  | "acquired" | "partnered_with" | "located_in";

type EvidentialRelation = "supports" | "contradicts" | "qualifies" | "weakens";
type LogicalRelation    = "implies" | "depends_on" | "decomposes_into";
type TemporalRelation   = "precedes" | "triggers" | "expires_at" | "valid_during";

interface Edge {
  id: EdgeId;
  type: "structural" | "evidential" | "logical" | "temporal";
  relation: StructuralRelation | EvidentialRelation | LogicalRelation | TemporalRelation;
  from: NodeId;
  to: NodeId;
  weight?: number;
  confidence: number;
  source_ref?: NodeId;
  created_at: ISODate;
  created_by: AuthorId;
  notes?: string;
}

// === 顶层图谱 ===

interface ResearchGraph {
  graph_id: string;
  name: string;
  mode: "mode_a_company" | "mode_b_narrative";
  anchor_node_id: NodeId;
  checklist_ref?: string;
  status: "active" | "completed" | "archived";
  created_at: ISODate;
  updated_at: ISODate;
  authors: AuthorId[];
  nodes: Node[];
  edges: Edge[];
}
```

## JSON 实例(微型例子)

```json
{
  "graph_id": "g_sk_hynix_v1",
  "name": "SK Hynix HBM 深度研究",
  "mode": "mode_a_company",
  "anchor_node_id": "n_sk_hynix",
  "checklist_ref": "checklists/value-investing-v1.md",
  "status": "active",
  "created_at": "2026-05-27T10:00:00Z",
  "updated_at": "2026-05-27T10:00:00Z",
  "authors": ["agent:shinkai-researcher-v1", "human:user"],
  "nodes": [
    {
      "id": "n_sk_hynix",
      "type": "Entity",
      "entity_kind": "Company",
      "canonical_name": "SK Hynix Inc.",
      "aliases": ["SK海力士", "Hynix"],
      "external_ids": { "ticker": "000660.KS", "isin": "KR7000660001" },
      "attributes": { "sector": "Semiconductors", "hq": "Icheon, South Korea" },
      "confidence": 1.0,
      "decay": { "half_life_days": 0 },
      "tags": ["semiconductors", "memory", "hbm", "ai-infrastructure"],
      "created_at": "2026-05-27T10:00:00Z",
      "created_by": "agent:shinkai-researcher-v1",
      "updated_at": "2026-05-27T10:00:00Z"
    },
    {
      "id": "n_claim_hbm_shortage",
      "type": "Claim",
      "statement": "HBM 是 AI 算力瓶颈,2025-2026 年仍供不应求",
      "claim_kind": "Forward",
      "temporal_scope": { "from": "2025-01-01", "to": "2026-12-31" },
      "subject_refs": ["n_sk_hynix"],
      "evidence_refs": ["n_evidence_nvda_24q1", "n_evidence_sk_capex"],
      "counter_evidence_refs": [],
      "confidence": 0.78,
      "decay": { "half_life_days": 180 },
      "tags": ["hbm", "supply-demand"],
      "created_at": "2026-05-27T10:00:00Z",
      "created_by": "agent:shinkai-researcher-v1",
      "updated_at": "2026-05-27T10:00:00Z"
    }
  ],
  "edges": [
    {
      "id": "e_001",
      "type": "structural",
      "relation": "supplies_to",
      "from": "n_sk_hynix",
      "to": "n_nvidia",
      "confidence": 0.95,
      "source_ref": "n_evidence_nvda_24q1",
      "created_at": "2026-05-27T10:00:00Z",
      "created_by": "agent:shinkai-researcher-v1"
    }
  ]
}
```

## 已知留待 v1 解决的问题

- **图谱合并**:当两份独立研究都创建了 `Apple` Entity,如何 dedupe / merge?(目前靠 `external_ids` 手动)
- **嵌套图谱**:Mode B 的图谱引用 Mode A 的子图,跨图引用的语义还没定义
- **版本快照**:研究中途如何 freeze 一个版本(用于做 backtest 或对比)
- **批量操作**:Agent 一次产生多个节点/边,事务性如何保证
- **存储后端**:JSON 文件 vs 图数据库(Neo4j) vs 关系库+JSONB — 暂不决策,先用 JSON 文件
