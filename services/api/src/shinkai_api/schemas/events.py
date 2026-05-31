from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run_start",
    "plan",
    "section_started",
    "section_completed",
    "item_started",
    "item_completed",
    "item_inconclusive",
    "step_start",
    "step_end",
    "thinking",
    "tool_call",
    "tool_result",
    "frontier_selected",
    "frontier_reprioritized",
    "role_step_completed",
    "supply_chain_layer_started",
    "frontier_expanded",
    "theme_discovered",
    "judgment_created",
    "candidate_created",
    "candidate_scored",
    "review_completed",
    "optimization_decision",
    "memory_patch_proposed",
    "filter_policy_patch_proposed",
    "checklist_patch_proposed",
    "research_task_created",
    "graph_delta",
    "evidence_found",
    "claim_created",
    "claim_validated",
    "claim_updated",
    "company_deep_analysis_completed",
    "company_dossier_created",
    "question_opened",
    "critic_warning",
    "checkpoint_raised",
    "checkpoint_released",
    "eval_completed",
    "child_run_created",
    "a2a_message_sent",
    "a2a_message_received",
    "artifact_written",
    "usage",
    "log",
    "error",
    "done",
]


class AgentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: EventType
    run_id: str | None = None
    step_id: str | None = None
    parent_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=lambda: time.time())
