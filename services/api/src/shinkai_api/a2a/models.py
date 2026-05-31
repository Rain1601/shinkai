from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["shinkai", "uteki"]
AgentMessageType = Literal[
    "candidate_handoff",
    "thesis_update",
    "challenge_claim",
    "monitoring_feedback",
    "memory_patch_proposal",
    "checklist_patch_proposal",
]


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    schema_version: str = "v0"
    from_agent: AgentName
    to_agent: AgentName
    type: AgentMessageType
    created_at: float = Field(default_factory=lambda: time.time())
    correlation_id: str
    priority: Literal["low", "normal", "high"] = "normal"
    requires_ack: bool = True
    status: Literal["queued", "delivered", "acked", "processed", "failed"] = "queued"
    payload: dict = Field(default_factory=dict)
