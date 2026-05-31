export type RunMode = "mode_a_company" | "mode_b_narrative";

export type AuthRole = "viewer" | "subscriber" | "admin";

export type ReadScope = "public" | "subscriber" | "admin";

export type AuthCapability =
  | "read_results"
  | "read_run_process"
  | "read_extended_results"
  | "read_extended_history"
  | "create_runs"
  | "control_runs"
  | "release_checkpoints"
  | "create_a2a_messages";

export type AuthSession = {
  auth_required: boolean;
  role: AuthRole;
  read_scope: ReadScope;
  capabilities: AuthCapability[];
};

export type RunStatus =
  | "created"
  | "running"
  | "paused"
  | "awaiting_checkpoint"
  | "completed"
  | "failed"
  | "aborted";

export type AgentEvent = {
  type: string;
  run_id?: string | null;
  step_id?: string | null;
  parent_id?: string | null;
  data: Record<string, unknown>;
  ts: number;
};

export type BudgetSpec = {
  max_wall_time_minutes: number;
  max_tool_calls: number;
  max_cost_usd?: number | null;
};

export type Run = {
  id: string;
  user_id: string;
  mode: RunMode;
  anchor: string;
  status: RunStatus;
  lifecycle_stage: string;
  parent_run_id?: string | null;
  child_run_ids: string[];
  graph_id?: string | null;
  checklist_ref?: string | null;
  scope: Record<string, unknown>;
  budget: BudgetSpec;
  events: AgentEvent[];
};

export type GraphNode = {
  id: string;
  type: "Entity" | "Claim" | "Evidence" | "Question" | "Thesis";
  confidence: number;
  data: Record<string, unknown>;
  tags: string[];
};

export type GraphEdge = {
  id: string;
  type: "structural" | "evidential" | "logical" | "temporal";
  relation: string;
  from_node: string;
  to_node: string;
  confidence: number;
  data: Record<string, unknown>;
};

export type ResearchGraph = {
  graph_id: string;
  run_id: string;
  mode: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type SourceTier = "primary" | "secondary" | "tertiary" | "agent_inference";

export type SourceType =
  | "web"
  | "sec"
  | "ir"
  | "news"
  | "filing"
  | "transcript"
  | "research_report"
  | "dataset"
  | "manual";

export type EvidenceKind =
  | "quote"
  | "summary"
  | "metric"
  | "filing_fact"
  | "transcript_excerpt"
  | "web_extract";

export type ClaimStatus = "unsupported" | "weak" | "supported" | "contradicted";

export type ClaimVerification = "support" | "refute" | "insufficient" | "stale";

export type CandidateStatus = "new" | "researching" | "qualified" | "rejected" | "watchlist";

export type TaskStatus = "queued" | "running" | "blocked" | "completed" | "failed";

export type SourceRef = {
  source_id: string;
  type: SourceType;
  tier: SourceTier;
  url: string;
  title: string;
  publisher: string;
  published_at?: number | null;
  primary_source_flag: boolean;
  accessed_at: number;
  reliability: number;
  metadata: Record<string, unknown>;
};

export type Evidence = {
  evidence_id: string;
  source_id: string;
  run_id: string;
  kind: EvidenceKind;
  text: string;
  url: string;
  quote: string;
  summary: string;
  citation_url: string;
  citation_anchor: string;
  citation_label: string;
  published_at?: number | null;
  extracted_at: number;
  confidence: number;
  supports_claim_ids: string[];
  metadata: Record<string, unknown>;
};

export type Claim = {
  claim_id: string;
  run_id: string;
  text: string;
  topic: string;
  status: ClaimStatus;
  verification: ClaimVerification;
  confidence: number;
  supporting_evidence_ids: string[];
  evidence_ids: string[];
  contradicting_evidence_ids: string[];
  stale_evidence_ids: string[];
  required_independent_sources: number;
  metadata: Record<string, unknown>;
};

export type CandidateCompany = {
  candidate_id: string;
  run_id: string;
  name: string;
  ticker: string;
  sector: string;
  supply_chain_layer: string;
  thesis: string;
  status: CandidateStatus;
  quality_score: number;
  under_coverage_score: number;
  relevance_score: number;
  claim_ids: string[];
  evidence_ids: string[];
  risk_flags: string[];
  next_questions: string[];
  metadata: Record<string, unknown>;
};

export type ResearchTask = {
  task_id: string;
  run_id: string;
  title: string;
  objective: string;
  parent_task_id?: string | null;
  status: TaskStatus;
  assigned_agent: string;
  claim_ids: string[];
  candidate_ids: string[];
  evidence_ids: string[];
  created_at: number;
  updated_at: number;
  metadata: Record<string, unknown>;
};

export type RunResearchState = {
  run_id: string;
  sources: SourceRef[];
  evidence: Evidence[];
  claims: Claim[];
  candidates: CandidateCompany[];
  tasks: ResearchTask[];
};

export type AgentMessageType =
  | "candidate_handoff"
  | "thesis_update"
  | "challenge_claim"
  | "monitoring_feedback"
  | "memory_patch_proposal"
  | "checklist_patch_proposal";

export type AgentMessage = {
  message_id: string;
  schema_version: string;
  from_agent: "shinkai" | "uteki";
  to_agent: "shinkai" | "uteki";
  type: AgentMessageType;
  created_at: number;
  correlation_id: string;
  priority: "low" | "normal" | "high";
  requires_ack: boolean;
  status: "queued" | "delivered" | "acked" | "processed" | "failed";
  payload: Record<string, unknown>;
};
