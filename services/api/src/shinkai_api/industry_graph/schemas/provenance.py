"""Provenance: who / when / where a fact came from.

Every entity, relation, attribute, and weight observation carries a list of
ProvenanceRef. No fact should live unattributed once it lands in the graph.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceType = Literal["hard_data", "soft_inference"]


class ProvenanceRef(BaseModel):
    """A single claim of evidence.

    `source_id` references a Source entity (kind="Source"). `quote` is the verbatim
    excerpt supporting the fact; `page` locates it. `evidence_type` distinguishes
    a direct hard-data assertion (e.g. table value) from a soft inference made by
    the agent reading the source.

    `asserted_at` is when the agent committed this provenance; `asserted_by` is
    the run/agent identifier so we can audit which run produced which facts.
    """

    model_config = ConfigDict(extra="allow")

    source_id: str
    page: int | None = None
    quote: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_type: EvidenceType = "hard_data"
    asserted_at: datetime
    asserted_by: str | None = None
