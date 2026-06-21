"""End-to-end runner: take a list of (tool_name, args) calls produced by an
LLM, dispatch them against an ``IndustryGraphStore`` and collect ToolResult.

Used by both the DeepSeek e2e test and the standalone ingestion script.

V0.5 polish (`docs/agent-tier-progression-v0.md` §1.3):
- #1 Repeated-call detection: if the agent calls the same tool with the same
  args ``REPEAT_THRESHOLD`` times in a row, the dispatcher feeds back a
  "you've already run this; change strategy" hint instead of executing again.
- #2 Auto source registration: the first write call without ``source_ref``
  triggers a synthetic ``register_source`` and the new ``source_id`` is
  injected into the current and subsequent writes.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

from shinkai_api.tools.base import ToolResult

from .service import IndustryGraphStore
from .tools import build_tools

REPEAT_THRESHOLD = 2  # 3rd identical call returns the hint instead of executing

# Tools that must NEVER auto-rewrite source_ref:
_QUERY_TOOLS = frozenset(
    {
        "find_entity",
        "get_entity",
        "find_relations",
        "walk_path",
        "find_bottlenecks",
        "find_key_data",
        "search_sources",
        "list_facet_values",
        "fulltext_search",
        "create_snapshot",
        "diff_snapshots",
        "revert_to",
        "list_recent_changes",
        "register_source",
    }
)


def _hash_call(name: str, args: dict[str, Any]) -> str:
    """Stable hash for (tool name, args) so we can detect exact repeats."""
    payload = json.dumps({"tool": name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


class ToolDispatcher:
    """Name → Tool lookup over a single :class:`IndustryGraphStore`."""

    def __init__(self, store: IndustryGraphStore) -> None:
        self.store = store
        self._tools = {t.name: t for t in build_tools(store)}
        # Sliding window of recent (hash, tool_name) so we can detect repeats.
        self._recent_calls: deque[tuple[str, str]] = deque(maxlen=REPEAT_THRESHOLD + 1)

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

    async def _auto_register_session_source(self, session_label: str) -> str | None:
        """Create a synthetic Source so first writes can chain off it.

        Returns the new source_id, or None if registration failed for some
        unforeseen reason.
        """
        date = datetime.now(UTC).date().isoformat()
        tool = self._tools.get("register_source")
        if tool is None:
            return None
        result = await tool.run(
            publisher="AGENT",
            title=f"Agent session {session_label}",
            date=date,
            slug_hint=f"agent_session_{session_label}_{date}",
        )
        if not result.ok:
            return None
        sid = result.data.get("source_id")
        return sid if isinstance(sid, str) else None

    async def run_calls(
        self, calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Execute a list of ``{"tool": name, "args": {...}}`` calls in order.

        Returns a list of result dicts with ``call_index``, ``tool``, ``ok``,
        ``summary``, and ``data``/``error``. Failures are reported but do not
        abort subsequent calls — the LLM may chain on best-effort.

        V0.5 conveniences:
        - If a write tool's ``source_ref.source_id`` is missing or empty, the
          dispatcher auto-fills it. The source_id comes from the most recent
          ``register_source`` call, or — if none exists yet — from a synthetic
          ``AGENT`` source the dispatcher auto-registers.
        - If the same (tool, args) hash repeats ``REPEAT_THRESHOLD`` times in a
          row, the dispatcher short-circuits and returns a hint instead of
          executing again.
        """
        out: list[dict[str, Any]] = []
        last_source_id: str | None = None
        for i, call in enumerate(calls):
            name = call.get("tool") or ""
            args = dict(call.get("args") or {})
            # ---- #2 Auto source_id injection ----
            if name not in _QUERY_TOOLS:
                ref = args.get("source_ref")
                has_sid = isinstance(ref, dict) and bool(ref.get("source_id"))
                if not has_sid:
                    if last_source_id is None:
                        last_source_id = await self._auto_register_session_source(
                            f"call{i:02d}"
                        )
                    if last_source_id:
                        args["source_ref"] = {
                            **(ref if isinstance(ref, dict) else {}),
                            "source_id": last_source_id,
                        }
            # ---- #1 Repeat-call detection ----
            call_hash = _hash_call(name, args)
            repeats = sum(1 for h, _ in self._recent_calls if h == call_hash)
            if repeats >= REPEAT_THRESHOLD:
                hint = (
                    f"You have already called `{name}` with these exact args "
                    f"{repeats} times in a row. Change strategy — pick a different "
                    "tool, vary the arguments, or output {\"tool\": \"done\"} if "
                    "you have enough information."
                )
                out.append(
                    {
                        "call_index": i,
                        "tool": name,
                        "ok": False,
                        "summary": hint,
                        "data": {"repeat_hint": True, "repeat_count": repeats},
                        "error": "repeated_call",
                    }
                )
                self._recent_calls.append((call_hash, name))
                continue
            # ---- dispatch ----
            result = await self.dispatch(name, args)
            # Track source_id from any successful register_source.
            if name == "register_source" and result.ok:
                sid = result.data.get("source_id") or result.data.get("entity_id")
                if isinstance(sid, str):
                    last_source_id = sid
            self._recent_calls.append((call_hash, name))
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
