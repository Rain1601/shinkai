"""End-to-end runner: take a list of (tool_name, args) calls produced by an
LLM, dispatch them against an ``IndustryGraphStore`` and collect ToolResult.

Used by both the DeepSeek e2e test and the standalone ingestion script.
"""

from __future__ import annotations

from typing import Any

from shinkai_api.tools.base import ToolResult

from .service import IndustryGraphStore
from .tools import build_tools


class ToolDispatcher:
    """Name → Tool lookup over a single :class:`IndustryGraphStore`."""

    def __init__(self, store: IndustryGraphStore) -> None:
        self.store = store
        self._tools = {t.name: t for t in build_tools(store)}

    def available_tools(self) -> list[dict[str, Any]]:
        """Tool name + description + JSON-Schema parameters — suitable to feed
        an LLM's system prompt or to attach to OpenAI-style tool calling."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def dispatch(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, summary=f"Unknown tool: {name}", error=name)
        try:
            return await tool.run(**args)
        except Exception as e:  # surface as ToolResult.error
            return ToolResult(ok=False, summary=str(e), error=type(e).__name__)

    async def run_calls(
        self, calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Execute a list of ``{"tool": name, "args": {...}}`` calls in order.

        Returns a list of result dicts with ``call_index``, ``tool``, ``ok``,
        ``summary``, and ``data``/``error``. Failures are reported but do not
        abort subsequent calls — the LLM may chain on best-effort.

        Convenience: if a write tool's ``source_ref.source_id`` is missing or
        empty, the dispatcher auto-fills it with the most recent
        ``register_source`` result's ``source_id``. This is the chain-pattern
        the prompt teaches but LLMs frequently flub.
        """
        out: list[dict[str, Any]] = []
        last_source_id: str | None = None
        for i, call in enumerate(calls):
            name = call.get("tool") or ""
            args = dict(call.get("args") or {})
            # Inject the most recent source_id into source_ref when blank.
            if name != "register_source" and last_source_id:
                ref = args.get("source_ref")
                if not isinstance(ref, dict) or not ref.get("source_id"):
                    args["source_ref"] = {
                        **(ref if isinstance(ref, dict) else {}),
                        "source_id": last_source_id,
                    }
            result = await self.dispatch(name, args)
            # Track the source_id for chaining.
            if name == "register_source" and result.ok:
                sid = result.data.get("source_id") or result.data.get("entity_id")
                if isinstance(sid, str):
                    last_source_id = sid
            out.append(
                {
                    "call_index": i,
                    "tool": name,
                    "ok": result.ok,
                    "summary": result.summary,
                    "data": result.data,
                    "error": result.error,
                }
            )
        return out


# Compact LLM system prompt for ingestion. The LLM is asked to emit a single
# JSON object ``{"calls": [...]}``; ``ToolDispatcher.run_calls`` then executes.
INGESTION_SYSTEM_PROMPT = """You are the ingestion agent for shinkai's industry graph.
You read short excerpts from equity research reports and emit a JSON object
``{"calls": [...]}`` listing the tools to invoke, in order, to capture the
facts in the excerpt. Each call is ``{"tool": <name>, "args": {...}}``.

Available tools (subset):
- register_source(publisher, title, date, pages?, tickers?, slug_hint?)
- upsert_entity(id, kind, labels, aliases?, description?, facets?, attributes?, source_ref)
- upsert_relation(type, source_id, target_id, weights?, attributes?, source_ref)
- add_bottleneck(slug, type, severity, description, affects, at_layer?, at_company?, source_ref)
- add_key_data(subject_id, metric, value, value_numeric?, unit?, period, slug?, source_ref)
- add_investment_thesis(target_id, slug, stocks_to_watch, bias, horizon, rationale, source_ref)
- create_snapshot(rationale, run_id?)

Rules:
1. ALWAYS register the source first; reuse the returned source_id in every subsequent source_ref.
2. Every write tool except register_source REQUIRES source_ref = {"source_id": <sid>, ...}.
3. Entity IDs: companies use "co:<TICKER>" (e.g. co:NVDA) or "co:<slug>".
4. Relation types: contains, themed_under, supplies_to, competes_with, produces,
   bottleneck_at, affects, key_data_about, watched_in.
5. Bottleneck.type ∈ {capacity, geopolitical, technology, demand, regulation}.
6. Bottleneck.severity ∈ {high, medium, low}.
7. End with create_snapshot{"rationale": "..."} so changes are committed.
8. Output JUST the JSON, no prose. Do NOT wrap in ```.
"""


__all__ = ["INGESTION_SYSTEM_PROMPT", "ToolDispatcher"]
