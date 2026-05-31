from __future__ import annotations

from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryLayer = Literal["working", "episodic", "semantic", "procedural"]


class MemoryEntry(BaseModel):
    entry_id: str
    layer: MemoryLayer
    run_id: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class WorkingMemoryItem(MemoryEntry):
    layer: MemoryLayer = "working"


class EpisodicRecord(MemoryEntry):
    """Run-level summary: what was the question, what did we conclude, was it right?"""

    layer: MemoryLayer = "episodic"
    anchor: str = ""
    outcome: str = ""
    eval_score: float | None = None
    consolidated_from: list[str] = Field(default_factory=list)


class SemanticFact(MemoryEntry):
    """Durable factual statement validated by primary sources."""

    layer: MemoryLayer = "semantic"
    subject: str = ""
    predicate: str = ""
    object_: str = Field(default="", alias="object")
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class ProceduralRecord(MemoryEntry):
    """A trajectory template: 'when context X, do Y first.'"""

    layer: MemoryLayer = "procedural"
    context_signature: str = ""
    action_sequence: list[str] = Field(default_factory=list)
    success_rate: float | None = None
