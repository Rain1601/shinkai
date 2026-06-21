"""Subjects layer — long-running investigation targets over the industry graph.

A ``Subject`` represents a thing we are continuously researching: either a
single ``Company`` (deep-dive its supply chain) or a ``Theme`` (track all the
companies under a SubTheme). Each agent analysis pass on a Subject is recorded
as a ``SubjectVersion`` — a thin layer over the existing snapshot system that
captures: which snapshot range this pass covered, what node ids the AgentLoop
actually touched (the "scope frontier"), and a change_summary computed by
intersecting that scope with the snapshot range.

The list/detail product surface in ``/industry-graph`` is built on top of this
module; the AgentLoop continues to do the actual graph mutation but now
publishes a SubjectVersion record on completion so the user can see what was
just done.
"""

from __future__ import annotations

from .models import (
    Subject,
    SubjectSchedule,
    SubjectType,
    SubjectVersion,
    SubjectVersionChangeSummary,
    SubjectVersionStatus,
    SubjectVersionTrigger,
)
from .store import SubjectStore

__all__ = [
    "Subject",
    "SubjectSchedule",
    "SubjectStore",
    "SubjectType",
    "SubjectVersion",
    "SubjectVersionChangeSummary",
    "SubjectVersionStatus",
    "SubjectVersionTrigger",
]
