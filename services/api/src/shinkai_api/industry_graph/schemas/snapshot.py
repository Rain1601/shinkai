"""Snapshot + change-entry schema.

Snapshots are incremental diffs against a parent (linear chain in V0; DAG in
V1+). Each snapshot has a `meta.json` describing the rationale and aggregate
counts, plus a `changes.jsonl` of individual insert/update/deprecate entries
with before/after state. Reconstruction replays changes from a base.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChangeOp = Literal["insert", "update", "deprecate"]
ChangeKind = Literal["entity", "relation"]


class ChangeEntry(BaseModel):
    """One mutation in a snapshot's changes.jsonl."""

    model_config = ConfigDict(extra="allow")

    op: ChangeOp
    kind: ChangeKind
    id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    source_ref_id: str | None = None
    actor: str | None = None
    ts: datetime


class ChangesetSummary(BaseModel):
    """Counts roll-up surfaced in snapshot meta for quick scan."""

    entities_added: int = 0
    entities_updated: int = 0
    entities_deprecated: int = 0
    relations_added: int = 0
    relations_updated: int = 0
    relations_deprecated: int = 0
    bottlenecks_added: int = 0
    key_data_added: int = 0
    theses_added: int = 0


class SnapshotMeta(BaseModel):
    """meta.json sibling of changes.jsonl in a snapshot directory."""

    model_config = ConfigDict(extra="allow")

    version: int
    parent_version: int | None = None
    created_at: datetime
    created_by_run_id: str | None = None
    rationale: str
    changeset_summary: ChangesetSummary = Field(default_factory=ChangesetSummary)
