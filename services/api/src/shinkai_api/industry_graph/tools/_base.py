"""Common Tool mixin for industry-graph tools.

Holds a reference to the IndustryGraphStore so each tool can mutate / query
the shared substrate. Tools are stateless besides this reference.
"""

from __future__ import annotations

from typing import Any

from shinkai_api.tools.base import Tool, ToolResult

from ..service import IndustryGraphStore

PROVENANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Evidence that backs this write. Required on all writes "
    "except register_source (chicken-and-egg).",
    "properties": {
        "source_id": {"type": "string"},
        "page": {"type": ["integer", "null"]},
        "quote": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0},
        "evidence_type": {
            "type": "string",
            "enum": ["hard_data", "soft_inference"],
            "default": "hard_data",
        },
    },
    "required": ["source_id"],
}


class IndustryGraphTool(Tool):
    """Tool subclass aware of the IndustryGraphStore."""

    def __init__(self, store: IndustryGraphStore) -> None:
        self._store = store

    @property
    def store(self) -> IndustryGraphStore:
        return self._store

    @staticmethod
    def _err(error: str) -> ToolResult:
        return ToolResult(ok=False, summary=error, error=error)

    @staticmethod
    def _ok(summary: str, data: dict[str, Any] | None = None) -> ToolResult:
        return ToolResult(ok=True, summary=summary, data=data or {})

    @staticmethod
    def _require_source_ref(kwargs: dict[str, Any]) -> tuple[str | None, str | None]:
        """Validate ``source_ref`` kwarg. Returns (source_id, error)."""
        ref = kwargs.get("source_ref")
        if not isinstance(ref, dict):
            return None, "Missing or invalid `source_ref` (expected dict)."
        sid = ref.get("source_id")
        if not isinstance(sid, str) or not sid:
            return None, "`source_ref.source_id` is required."
        return sid, None
