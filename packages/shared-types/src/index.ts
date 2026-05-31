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
