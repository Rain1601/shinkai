"""Snapshot & audit tools — commit, diff, revert, list changes."""

from __future__ import annotations

from typing import Any

from shinkai_api.tools.base import ToolResult

from ._base import IndustryGraphTool


class CreateSnapshotTool(IndustryGraphTool):
    name = "create_snapshot"
    description = "Package pending changes into a numbered snapshot and clear pending."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "rationale": {"type": "string"},
            "run_id": {"type": ["string", "null"]},
        },
        "required": ["rationale"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        rationale = kwargs.get("rationale")
        if not rationale:
            return self._err("`rationale` is required.")
        pending_count = len(self.store.pending)
        if pending_count == 0:
            return self._ok("No pending changes; snapshot not created.", {"version": None})
        meta = await self.store.commit_snapshot(
            rationale=rationale,
            created_by_run_id=kwargs.get("run_id"),
        )
        return self._ok(
            f"Snapshot v{meta.version} committed ({pending_count} changes).",
            {
                "version": meta.version,
                "parent_version": meta.parent_version,
                "summary": meta.changeset_summary.model_dump(),
            },
        )


class DiffSnapshotsTool(IndustryGraphTool):
    name = "diff_snapshots"
    description = "Return the changeset between two snapshot versions."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "v_from": {"type": "integer"},
            "v_to": {"type": "integer"},
        },
        "required": ["v_from", "v_to"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        v_from = int(kwargs["v_from"])
        v_to = int(kwargs["v_to"])
        diff = await self.store.snapshots.diff(v_from, v_to)
        return self._ok(
            f"Diff v{v_from} → v{v_to}: {len(diff)} entries.",
            {"changes": [c.model_dump(mode="json") for c in diff]},
        )


class RevertToTool(IndustryGraphTool):
    name = "revert_to"
    description = (
        "Reconstruct state at an earlier snapshot version. "
        "Currently returns the projected state — actual rollback is V1+."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "version": {"type": "integer"},
            "rationale": {"type": "string"},
        },
        "required": ["version", "rationale"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        version = int(kwargs["version"])
        current = {
            "entities": dict(self.store.index.by_id),
            "relations": dict(self.store.index.relations_by_id),
        }
        projected = await self.store.snapshots.reconstruct_state(current, version)
        return self._ok(
            f"Projected state at v{version}: {len(projected['entities'])} entities, "
            f"{len(projected['relations'])} relations.",
            {
                "version": version,
                "entity_count": len(projected["entities"]),
                "relation_count": len(projected["relations"]),
            },
        )


class ListRecentChangesTool(IndustryGraphTool):
    name = "list_recent_changes"
    description = "Audit log query — recent ChangeEntries from audit.jsonl."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "since": {"type": ["string", "null"], "description": "ISO timestamp"},
            "by_run_id": {"type": ["string", "null"]},
            "limit": {"type": "integer", "default": 100},
        },
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        since = kwargs.get("since")
        by_run_id = kwargs.get("by_run_id")
        limit = int(kwargs.get("limit") or 100)
        entries = await self.store.fs.read_audit()
        if since:
            entries = [e for e in entries if (e.get("ts") or "") >= since]
        if by_run_id:
            entries = [e for e in entries if e.get("actor") == by_run_id]
        entries = entries[-limit:]
        return self._ok(f"Returning {len(entries)} change entries.", {"changes": entries})


__all__ = [
    "CreateSnapshotTool",
    "DiffSnapshotsTool",
    "ListRecentChangesTool",
    "RevertToTool",
]
