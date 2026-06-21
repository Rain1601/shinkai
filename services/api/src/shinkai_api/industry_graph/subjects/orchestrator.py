"""Run a SubjectVersion analysis pass end-to-end.

This is the only module that knows how to:
1. Acquire the per-Subject run lock (raising ``SubjectLockBusy`` on contention).
2. Generate the task prompt that fits the Subject's analytical mode
   (Company vs Theme — see the plan's "AgentLoop integration" section).
3. Record a pending SubjectVersion, drive the AgentLoop, and write the
   final ``status``, ``ended_at``, ``scope_node_ids``, and ``change_summary``
   on completion (or ``error`` + status=failed on a thrown exception).

The actual graph mutation continues to happen inside AgentLoop; the
orchestrator is the thin wrapper that connects that loop to the Subjects
domain model.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from shinkai_api.llm.deepseek import DeepSeekClient

from ..agent_loop import AgentLoop
from ..schemas.snapshot import ChangeEntry
from ..service import IndustryGraphStore
from .models import (
    Subject,
    SubjectVersion,
    SubjectVersionChangeSummary,
    SubjectVersionTrigger,
)
from .store import SubjectStore

# Default budgets — kept conservative for V0. POST handler can override.
DEFAULT_MAX_TURNS = 20
DEFAULT_MAX_TOKENS_PER_TURN = 1500
DEFAULT_TEMPERATURE = 0.2


def build_task_prompt(subject: Subject) -> str:
    """Generate the natural-language task the AgentLoop should pursue.

    Each Subject type gets a different lens, mirroring the user's framing:
    Company subjects are deep-dives on one giant's supply chain; Theme
    subjects enumerate companies under a theme and their interrelations.
    """
    target = subject.target_entity_id
    name = subject.display_name
    if subject.type == "company":
        return (
            f"Review the supply chain for {name} ({target}).\n"
            "1. find_entity(query=<name>) to confirm the anchor is present, "
            "then walk its direct relations with find_relations(source_id) "
            "and find_relations(target_id).\n"
            "2. Identify any new direct suppliers, customers, or competitors "
            "that should plausibly be in the graph but are not yet — add them "
            "with upsert_entity and create the supplies_to / competes_with "
            "relations. Use facets.supply_layer per the strata vocabulary.\n"
            "3. Flag any new technology or capacity bottlenecks affecting "
            f"{name} via add_bottleneck.\n"
            "4. Take create_snapshot with a one-line rationale, then emit "
            '{"tool":"done","summary":"…"}.\n'
            "Cite an AGENT session source for everything new. Do NOT remove "
            "existing nodes."
        )
    if subject.type == "theme":
        return (
            f"Survey the {name} theme ({target}).\n"
            "1. find_entity(kind='Company', facets={'subtheme': [<theme id>]}) "
            "to list companies already attached to this theme.\n"
            "2. For each, walk find_relations to capture the strongest "
            "supplier / customer / competitor relations.\n"
            "3. Identify companies newly emerging in this theme that are not "
            "yet in the graph and add them with the correct supply_layer.\n"
            "4. Take create_snapshot with a one-line rationale, then emit "
            '{"tool":"done","summary":"…"}.\n'
            "Cite an AGENT session source for everything new."
        )
    raise ValueError(f"Unknown subject type: {subject.type}")


def _normalize_scope(touched: list[str]) -> list[str]:
    """Drop relation ids (start with `r:`) from the scope frontier — relations
    are inferred from their endpoints. Sorted for determinism."""
    return sorted({i for i in touched if not i.startswith("r:")})


async def compute_change_summary(
    graph: IndustryGraphStore,
    *,
    snapshot_from: int,
    snapshot_to: int,
    scope_node_ids: list[str],
) -> SubjectVersionChangeSummary | None:
    """Walk ChangeEntries in (snapshot_from, snapshot_to] and roll them up,
    restricted to anything whose id (entities) or endpoint (relations) is
    in ``scope_node_ids``. Returns ``None`` when the window is empty AND the
    scope is empty (nothing to report)."""
    if snapshot_to <= snapshot_from and not scope_node_ids:
        return None
    if snapshot_to <= snapshot_from:
        # Window has no new commits; everything in scope was a no-op observation.
        return SubjectVersionChangeSummary()
    scope = set(scope_node_ids)
    s = SubjectVersionChangeSummary()
    highlights: list[str] = []

    def _matches(c: ChangeEntry) -> bool:
        if c.kind == "entity":
            return c.id in scope
        # relation: match if either endpoint touched
        rec = c.after or c.before or {}
        return rec.get("source_id") in scope or rec.get("target_id") in scope or c.id in scope

    for v in range(snapshot_from + 1, snapshot_to + 1):
        changes = await graph.snapshots.load_changes(v)
        for c in changes:
            if not _matches(c):
                continue
            if c.kind == "entity":
                if c.op == "insert":
                    s.entities_added += 1
                    label = ((c.after or {}).get("labels") or [c.id])[0]
                    highlights.append(f"+ {label}")
                elif c.op == "update":
                    s.entities_updated += 1
                elif c.op == "deprecate":
                    s.entities_deprecated += 1
            else:  # relation
                if c.op == "insert":
                    s.relations_added += 1
                elif c.op == "update":
                    s.relations_updated += 1
                elif c.op == "deprecate":
                    s.relations_deprecated += 1
    s.highlights = highlights[:8]  # cap for the timeline card
    return s


async def prepare_subject_run(
    *,
    subject: Subject,
    subject_store: SubjectStore,
    graph_store: IndustryGraphStore,
    triggered_by: SubjectVersionTrigger = "manual",
    task_override: str | None = None,
) -> SubjectVersion:
    """Synchronously claim the next version slot for this subject.

    Caller MUST already hold ``subject_store._lock_for(subject.id)`` so
    version_no allocation + pending row write are race-free with respect to
    concurrent POSTs. Returns the pending SubjectVersion (status=running).
    """
    version_no = await subject_store.next_version_no(subject.id)
    snapshot_from = await graph_store.snapshots.latest_version()
    slug = subject.id.split(":", 1)[1] if ":" in subject.id else subject.id
    sv_id = f"sv:{slug}:{version_no}"
    run_id = secrets.token_hex(4)
    task = task_override if task_override is not None else build_task_prompt(subject)
    started = datetime.now(UTC)

    pending = SubjectVersion(
        id=sv_id,
        subject_id=subject.id,
        version_no=version_no,
        run_id=run_id,
        snapshot_from=snapshot_from,
        snapshot_to=snapshot_from,  # unknown until done
        triggered_by=triggered_by,
        status="running",
        started_at=started,
        task_prompt=task,
        rationale="",
    )
    await subject_store.upsert_version(pending)
    return pending


async def finish_subject_run(
    *,
    pending: SubjectVersion,
    subject_store: SubjectStore,
    graph_store: IndustryGraphStore,
    client: DeepSeekClient,
    max_turns: int = DEFAULT_MAX_TURNS,
    max_tokens_per_turn: int = DEFAULT_MAX_TOKENS_PER_TURN,
    temperature: float = DEFAULT_TEMPERATURE,
    agent_factory: Callable[..., Awaitable[dict]] | None = None,
) -> SubjectVersion:
    """Drive the AgentLoop for an already-pending SubjectVersion and write the
    final record. On exception, persists status=failed before re-raising.

    ``agent_factory`` is an injection seam for tests: when provided, it's
    awaited instead of the real AgentLoop.run() and must return the same
    summary dict shape (session_id, touched_ids, done_summary, …).
    """
    try:
        if agent_factory is not None:
            summary = await agent_factory(
                subject_id=pending.subject_id,
                graph_store=graph_store,
                client=client,
                task=pending.task_prompt,
                run_id=pending.run_id,
            )
        else:
            loop = AgentLoop(
                store=graph_store,
                client=client,
                task=pending.task_prompt,
                max_turns=max_turns,
                max_tokens_per_turn=max_tokens_per_turn,
                temperature=temperature,
                session_id=pending.run_id,
            )
            summary = await loop.run()
    except Exception as e:
        ended = datetime.now(UTC)
        await subject_store.update_version_status(
            pending.id, status="failed", ended_at=ended, error=str(e),
        )
        raise

    snapshot_to = await graph_store.snapshots.latest_version()
    scope = _normalize_scope(summary.get("touched_ids", []))
    change_summary = await compute_change_summary(
        graph_store,
        snapshot_from=pending.snapshot_from,
        snapshot_to=snapshot_to,
        scope_node_ids=scope,
    )

    ended = datetime.now(UTC)
    final = pending.model_copy(
        update={
            "status": "completed",
            "ended_at": ended,
            "snapshot_to": snapshot_to,
            "scope_node_ids": scope,
            "rationale": summary.get("done_summary") or "",
            "change_summary": change_summary,
        }
    )
    await subject_store.upsert_version(final)
    return final


async def run_subject_analysis(
    *,
    subject: Subject,
    subject_store: SubjectStore,
    graph_store: IndustryGraphStore,
    client: DeepSeekClient,
    triggered_by: SubjectVersionTrigger = "manual",
    max_turns: int = DEFAULT_MAX_TURNS,
    max_tokens_per_turn: int = DEFAULT_MAX_TOKENS_PER_TURN,
    temperature: float = DEFAULT_TEMPERATURE,
    task_override: str | None = None,
    agent_factory: Callable[..., Awaitable[dict]] | None = None,
) -> SubjectVersion:
    """All-in-one: acquire the run lock, prepare a pending version, drive
    the agent, write the final record. Used by tests and by the scheduled
    trigger; the POST handler uses ``prepare_subject_run`` + ``finish_subject_run``
    directly so it can hold the lock across HTTP boundary.
    """
    async with subject_store.run_lock(subject.id):
        pending = await prepare_subject_run(
            subject=subject,
            subject_store=subject_store,
            graph_store=graph_store,
            triggered_by=triggered_by,
            task_override=task_override,
        )
        return await finish_subject_run(
            pending=pending,
            subject_store=subject_store,
            graph_store=graph_store,
            client=client,
            max_turns=max_turns,
            max_tokens_per_turn=max_tokens_per_turn,
            temperature=temperature,
            agent_factory=agent_factory,
        )


__all__ = [
    "build_task_prompt",
    "compute_change_summary",
    "finish_subject_run",
    "prepare_subject_run",
    "run_subject_analysis",
]
