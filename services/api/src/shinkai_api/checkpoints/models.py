from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckpointStatus = Literal["pending", "approved", "rejected", "released"]


class CheckpointDecision(BaseModel):
    decision: Literal["approve", "reject", "inject", "abort"]
    comments: str = ""
    payload: dict = Field(default_factory=dict)


class Checkpoint(BaseModel):
    id: str
    run_id: str
    status: CheckpointStatus = "pending"
    reason: str
    packet_artifact_id: str | None = None
    decision: CheckpointDecision | None = None
