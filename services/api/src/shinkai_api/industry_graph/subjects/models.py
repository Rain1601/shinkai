"""Pydantic schemas for Subject + SubjectVersion.

Field shapes were kept deliberately close to ``runs/models.py`` (status enum,
started_at / ended_at, triggered_by) so that if/when we promote SubjectVersion
to run on the full RunExecutor pipeline, the migration is mechanical.

``change_summary`` is nullable on purpose: the migration backfill creates a
synthetic v1 with ``change_summary = None`` because there is no real diff to
compute from pre-existing snapshot state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SubjectType = Literal["company", "theme"]
SubjectVersionStatus = Literal["pending", "running", "completed", "failed"]
SubjectVersionTrigger = Literal["manual", "schedule", "agent", "migration"]


class SubjectSchedule(BaseModel):
    """Optional cron-style schedule for autonomous reruns."""

    model_config = ConfigDict(extra="allow")

    cron: str | None = None
    autonomous: bool = False


class Subject(BaseModel):
    """A long-lived investigation target.

    Companies and Themes are the two flavors at V0; the model is open to
    extension via ``model_config = extra='allow'`` so future analysis modes
    can attach extra fields without a migration.
    """

    model_config = ConfigDict(extra="allow")

    id: str  # subj:<slug>
    type: SubjectType
    display_name: str
    # Pointer into the graph: co:<TICKER> for company, st:<slug> (SubTheme id)
    # for theme subjects.
    target_entity_id: str
    schedule: SubjectSchedule = Field(default_factory=SubjectSchedule)
    created_at: datetime
    updated_at: datetime


class SubjectVersionChangeSummary(BaseModel):
    """Rollup of changes in a SubjectVersion's snapshot range, restricted to
    ``scope_node_ids`` (so we count what this version is actually about).

    Counts are computed at completion time and stored, so callers don't have
    to re-derive from the change journal.
    """

    model_config = ConfigDict(extra="allow")

    entities_added: int = 0
    entities_updated: int = 0
    entities_deprecated: int = 0
    relations_added: int = 0
    relations_updated: int = 0
    relations_deprecated: int = 0
    # Convenience labels for the timeline card (e.g. ["+ SK Innovation", "+ KDP 2027 growth"]).
    highlights: list[str] = Field(default_factory=list)


class SubjectVersion(BaseModel):
    """One analysis pass over a Subject.

    Identity: ``id = sv:<subj_slug>:<v#>``. ``version_no`` is monotonically
    increasing per ``subject_id``; it does not correspond to the global
    snapshot version.

    Snapshot range: ``snapshot_from`` is the global snapshot version at the
    moment the run started; ``snapshot_to`` is whatever the head version is
    when the run completes. Equal when the agent did not commit anything new.

    Scope: ``scope_node_ids`` is the set of entity ids the AgentLoop touched
    across its tool calls. This is captured by inspecting AgentLoop.actions
    and is what makes change_summary computable later from any snapshot
    range without ambiguity.
    """

    model_config = ConfigDict(extra="allow")

    id: str  # sv:<subj_slug>:<v#>
    subject_id: str
    version_no: int
    run_id: str  # AgentLoop session id (hex)
    snapshot_from: int
    snapshot_to: int
    triggered_by: SubjectVersionTrigger
    status: SubjectVersionStatus
    started_at: datetime
    ended_at: datetime | None = None
    scope_node_ids: list[str] = Field(default_factory=list)
    task_prompt: str = ""
    rationale: str = ""
    change_summary: SubjectVersionChangeSummary | None = None
    error: str | None = None


__all__ = [
    "Subject",
    "SubjectSchedule",
    "SubjectType",
    "SubjectVersion",
    "SubjectVersionChangeSummary",
    "SubjectVersionStatus",
    "SubjectVersionTrigger",
]
