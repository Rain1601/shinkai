from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from shinkai_api.schemas.events import AgentEvent

RunMode = Literal["mode_a_company", "mode_b_narrative"]
RunStatus = Literal[
    "created",
    "running",
    "paused",
    "awaiting_checkpoint",
    "completed",
    "failed",
    "aborted",
]
TriggeredBy = Literal["user", "cron", "event", "eval", "compare", "a2a"]


class BudgetSpec(BaseModel):
    max_wall_time_minutes: int = 120
    max_tool_calls: int = 200
    max_cost_usd: float | None = None


class RunCreate(BaseModel):
    mode: RunMode = "mode_b_narrative"
    anchor: str = "Autonomous Discovery"
    scope: dict = Field(default_factory=dict)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    parent_run_id: str | None = None
    triggered_by: TriggeredBy = "user"
    trigger_reason: str = ""


class UsageSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Run(BaseModel):
    id: str
    user_id: str = "local"
    mode: RunMode
    anchor: str
    status: RunStatus = "created"
    lifecycle_stage: str = "created"
    parent_run_id: str | None = None
    child_run_ids: list[str] = Field(default_factory=list)
    graph_id: str | None = None
    checklist_ref: str | None = None
    triggered_by: TriggeredBy = "user"
    trigger_reason: str = ""
    scope: dict = Field(default_factory=dict)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    events: list[AgentEvent] = Field(default_factory=list)
    usage_summary: UsageSummary = Field(default_factory=UsageSummary)
