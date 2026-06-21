"""Multi-turn agentic loop over the industry-graph tool surface.

The LLM does NOT read external research text. It receives only:
1. A task (one sentence describing what to do).
2. The full tool catalogue (names + JSON-Schema parameters).
3. Tool execution results from prior turns.

Each turn the LLM emits exactly one tool call as JSON; the loop dispatches it,
appends the result to the conversation, and asks again. The session ends when
the LLM emits ``{"tool": "done", "summary": "..."}`` or the turn budget runs out.

This is the canonical "agent reasons with its world model + a structured action
space, no documents in the prompt" pattern. Research reports come in only via
already-ingested seed data that the agent can discover with ``find_*`` /
``get_entity`` query tools.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from shinkai_api.llm.deepseek import DeepSeekClient, DeepSeekError

from .e2e_runner import ToolDispatcher
from .service import IndustryGraphStore

AGENT_SYSTEM_PROMPT = """You are an autonomous agent operating shinkai's industry knowledge graph.

# Operating mode
- You output EXACTLY ONE JSON object per turn: {"tool": <name>, "args": {...}}.
- No prose, no markdown, no code fences. Just the JSON object.
- The next user message will be the tool's execution result; use it to decide the next action.
- When the task is complete, output exactly: {"tool": "done", "summary": "<one-sentence outcome>"}.
- You have a fixed turn budget; plan accordingly.

# How to think
- You are NOT reading a research report. You are reasoning from:
  (a) your own world knowledge, (b) what query tools reveal about the current graph.
- Start by EXPLORING: call find_entity / get_entity / find_relations / find_bottlenecks
  to learn what is already in the graph.
- Then identify gaps relevant to the task and use write tools to fill them.
- Take a create_snapshot when a meaningful chunk is done.

# Tool catalogue (key fields shown; full JSON Schemas already known to you)

Query tools (no source_ref needed):
- find_entity(query?, kind?, facets?, limit?)
- get_entity(id)
- find_relations(source_id?, target_id?, type?, period?)
- find_bottlenecks(anchor_id?, type?, severity_min?)
- find_key_data(subject_id, metric_substr?, period?)
- walk_path(from_id, to_id, max_depth?, edge_types?)
- list_facet_values(facet_name)
- search_sources(publisher?, ticker?, date_from?, date_to?)
- fulltext_search(query, limit?)

Write tools (REQUIRE source_ref; see below for schema):
- upsert_entity(id, kind, labels, aliases?, description?, facets?, attributes?, source_ref)
- upsert_relation(type, source_id, target_id, weights?, attributes?, source_ref)
- add_bottleneck(slug, type, severity, description, affects, at_layer?, at_company?, source_ref)
- add_key_data(subject_id, metric, value, value_numeric?, unit?, period, slug?, source_ref)
- add_investment_thesis(target_id, slug, stocks_to_watch, bias, horizon, rationale, source_ref)
- set_attribute(entity_id, key, value, source_ref)
- add_alias(entity_id, alias, source_ref)
- add_facet_value(entity_id, facet_name, value, source_ref)
- deprecate_entity(entity_id, reason, source_ref)
- deprecate_relation(relation_id, reason, source_ref)

source_ref schema (object):
- source_id: str (required)
- page: int (optional)
- quote: str (optional)
- confidence: float 0.0-1.0 (optional, default 1.0)
- evidence_type: "hard_data" | "soft_inference" (optional, default "hard_data")

Source registration:
- register_source(publisher, title, date, ...) — call ONCE near the start
  of the session. Use publisher="AGENT" and title="Agent session <id>".
  The dispatcher will auto-fill source_ref.source_id on subsequent writes,
  so you may pass source_ref={} or omit it on write calls if you wish.

Snapshot & end:
- create_snapshot(rationale)
- {"tool": "done", "summary": "..."}  — end the session

# Constraints
- IDs follow the convention:
    co:<TICKER> (e.g. co:NVDA, co:2330.TW) — Company
    bn:<slug>   — Bottleneck (let add_bottleneck derive it from slug)
    kdp:<slug>  — KeyDataPoint
- Bottleneck.type must be in {capacity, geopolitical, technology, demand, regulation}.
- Bottleneck.severity must be in {high, medium, low}.
- InvestmentThesis.stocks_to_watch is a LIST OF OBJECTS, each like
  {"ticker": "NVDA", "rationale": "...", "pt": "$X" (optional)}.
- Anything that would feel like "inferred but not directly observed" should use
  evidence_type="soft_inference" with lower confidence (e.g. 0.6-0.8).

Begin.
"""


def _truncate(s: str, limit: int = 1500) -> str:
    """Trim a string for context-budget reasons."""
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n... [truncated {len(s) - limit} chars]"


def _serialize_tool_result(name: str, result: dict[str, Any]) -> str:
    """Format a dispatcher result as a short user message for the LLM."""
    flag = "OK" if result.get("ok") else "ERROR"
    summary = result.get("summary") or ""
    data = result.get("data") or {}
    body = json.dumps(data, ensure_ascii=False, default=str, indent=2)
    return f"[tool {name} → {flag}] {summary}\n---\n{_truncate(body)}"


class AgentLoop:
    """Drive an LLM through a multi-turn tool-use session."""

    def __init__(
        self,
        *,
        store: IndustryGraphStore,
        client: DeepSeekClient,
        task: str,
        max_turns: int = 20,
        max_tokens_per_turn: int = 1200,
        temperature: float = 0.2,
    ) -> None:
        self.store = store
        self.dispatcher = ToolDispatcher(store)
        self.client = client
        self.task = task
        self.max_turns = max_turns
        self.max_tokens_per_turn = max_tokens_per_turn
        self.temperature = temperature
        self.session_id = secrets.token_hex(4)
        self.history: list[dict[str, str]] = []
        self.actions: list[dict[str, Any]] = []
        self._done_summary: str | None = None

    def _seed_history(self) -> None:
        """Initial system + task messages. No research text."""
        self.history = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"# TASK (session {self.session_id}, max {self.max_turns} turns)\n\n"
                    f"{self.task}\n\n"
                    "Begin by exploring the graph with query tools, then act. "
                    "Remember: emit only ONE JSON object per turn."
                ),
            },
        ]

    async def _llm_step(self) -> dict[str, Any]:
        """Ask the LLM for the next tool call (as JSON)."""
        return await self.client.chat_messages_json(
            messages=self.history,
            temperature=self.temperature,
            max_tokens=self.max_tokens_per_turn,
        )

    async def run(self) -> dict[str, Any]:
        """Execute up to ``max_turns`` turns. Returns a summary dict."""
        started_at = datetime.now(UTC).isoformat()
        self._seed_history()

        for turn in range(self.max_turns):
            try:
                call = await self._llm_step()
            except DeepSeekError as e:
                self.actions.append(
                    {"turn": turn, "tool": None, "ok": False, "error": str(e)}
                )
                break

            # Strip helper fields injected by chat_messages_json.
            call.pop("_usage", None)

            tool_name = call.get("tool")
            args = call.get("args") or {}

            if tool_name == "done":
                self._done_summary = call.get("summary") or ""
                self.actions.append(
                    {"turn": turn, "tool": "done", "ok": True, "summary": self._done_summary}
                )
                break

            if not isinstance(tool_name, str):
                # Malformed turn: tell the LLM and continue.
                err_msg = (
                    "Your last message was not a valid tool call. "
                    'Output exactly {"tool":..., "args":{...}}.'
                )
                self.history.append({"role": "assistant", "content": json.dumps(call)})
                self.history.append({"role": "user", "content": err_msg})
                self.actions.append(
                    {"turn": turn, "tool": None, "ok": False, "error": "malformed"}
                )
                continue

            # Execute through the dispatcher (auto source_id injection lives there).
            results = await self.dispatcher.run_calls([{"tool": tool_name, "args": args}])
            result = results[0]
            self.actions.append(
                {
                    "turn": turn,
                    "tool": tool_name,
                    "ok": result["ok"],
                    "summary": result["summary"],
                    "error": result.get("error"),
                }
            )

            # Append the LLM's call and the tool result to history.
            self.history.append({"role": "assistant", "content": json.dumps(call)})
            self.history.append(
                {"role": "user", "content": _serialize_tool_result(tool_name, result)}
            )
        else:
            # Loop fell off without 'done'.
            self.actions.append(
                {"turn": self.max_turns, "tool": None, "ok": False, "error": "max_turns_reached"}
            )

        finished_at = datetime.now(UTC).isoformat()
        return {
            "session_id": self.session_id,
            "task": self.task,
            "turns_used": len([a for a in self.actions if a.get("tool")]),
            "done_summary": self._done_summary,
            "started_at": started_at,
            "finished_at": finished_at,
            "actions": self.actions,
            "store_stats": self.store.stats(),
        }


__all__ = ["AGENT_SYSTEM_PROMPT", "AgentLoop"]
