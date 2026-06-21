"""Snapshot + incremental diff layer.

A snapshot is a directory ``snapshots/v{N:04d}/`` holding:
- ``meta.json`` — :class:`SnapshotMeta` payload (version, parent, summary).
- ``changes.jsonl`` — one :class:`ChangeEntry` per line, ordered.

The ``current/`` directory is always the fully-resolved state at the latest
version. Reconstruction of an older version replays changes backwards from
``current/`` (V0: linear chain only — branches land in V1+).
"""

from __future__ import annotations

import copy
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from ..schemas import (
    ChangeEntry,
    ChangesetSummary,
    SnapshotMeta,
)
from .file_store import IndustryGraphFileStore


def _classify_summary(changes: list[ChangeEntry]) -> ChangesetSummary:
    """Roll ChangeEntry list up into a ChangesetSummary for meta.json."""
    s = ChangesetSummary()
    for c in changes:
        if c.kind == "entity":
            kind_str = (c.after or c.before or {}).get("kind")
            if c.op == "insert":
                s.entities_added += 1
                if kind_str == "Bottleneck":
                    s.bottlenecks_added += 1
                elif kind_str == "KeyDataPoint":
                    s.key_data_added += 1
                elif kind_str == "InvestmentThesis":
                    s.theses_added += 1
            elif c.op == "update":
                s.entities_updated += 1
            elif c.op == "deprecate":
                s.entities_deprecated += 1
        elif c.kind == "relation":
            if c.op == "insert":
                s.relations_added += 1
            elif c.op == "update":
                s.relations_updated += 1
            elif c.op == "deprecate":
                s.relations_deprecated += 1
    return s


class SnapshotManager:
    """Manages snapshot directories, change recording, and reconstruction.

    The manager itself is stateless w.r.t. pending changes — callers (a higher
    "Store" assembling tool-level writes) pass the full ``ChangeEntry`` list to
    :meth:`commit`. ``parent_version`` is derived from the file store's existing
    versions; the new snapshot version is parent+1.
    """

    def __init__(self, file_store: IndustryGraphFileStore) -> None:
        self.fs = file_store

    async def latest_version(self) -> int:
        versions = await self.fs.list_snapshot_versions()
        return max(versions) if versions else 0

    async def commit(
        self,
        *,
        rationale: str,
        changes: list[ChangeEntry],
        created_by_run_id: str | None = None,
    ) -> SnapshotMeta:
        """Persist a new snapshot recording ``changes``. Returns the meta."""
        parent = await self.latest_version()
        version = parent + 1
        meta = SnapshotMeta(
            version=version,
            parent_version=parent if parent > 0 else None,
            created_at=datetime.now(UTC),
            created_by_run_id=created_by_run_id,
            rationale=rationale,
            changeset_summary=_classify_summary(changes),
        )
        await self.fs.persist_snapshot(
            version=version,
            meta=meta.model_dump(mode="json"),
            changes=[c.model_dump(mode="json") for c in changes],
        )
        return meta

    async def load_meta(self, version: int) -> SnapshotMeta | None:
        raw = await self.fs.load_snapshot_meta(version)
        if raw is None:
            return None
        return SnapshotMeta.model_validate(raw)

    async def load_changes(self, version: int) -> list[ChangeEntry]:
        raws = await self.fs.load_snapshot_changes(version)
        return [ChangeEntry.model_validate(r) for r in raws]

    async def diff(self, v_from: int, v_to: int) -> list[ChangeEntry]:
        """All changes applied from ``v_from`` (exclusive) up to ``v_to`` (inclusive).

        If ``v_from > v_to`` we return the inverse: the entries that would undo
        ``v_to..v_from`` (each ``insert`` becomes ``deprecate`` and vice versa,
        ``update`` swaps before/after).
        """
        forward = v_from < v_to
        lo, hi = (v_from, v_to) if forward else (v_to, v_from)
        chain: list[ChangeEntry] = []
        for v in range(lo + 1, hi + 1):
            chain.extend(await self.load_changes(v))
        if forward:
            return chain
        return [_invert(c) for c in reversed(chain)]

    async def reconstruct_state(
        self, current_state: dict[str, dict[str, dict[str, Any]]], target_version: int
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Replay diffs backwards from ``current_state`` to reach ``target_version``.

        ``current_state`` is shaped::

            {
                "entities": {id: record, ...},
                "relations": {id: record, ...},
            }

        Returns a new dict; the input is not mutated.
        """
        latest = await self.latest_version()
        if target_version > latest:
            raise ValueError(
                f"Target version {target_version} > latest {latest}"
            )
        state = {
            "entities": copy.deepcopy(current_state.get("entities", {})),
            "relations": copy.deepcopy(current_state.get("relations", {})),
        }
        # Undo changes from latest down to (target_version + 1).
        for v in range(latest, target_version, -1):
            changes = await self.load_changes(v)
            for c in reversed(changes):
                _apply_inverse(state, c)
        return state


def _invert(c: ChangeEntry) -> ChangeEntry:
    """Return the change that would undo ``c``."""
    if c.op == "insert":
        new_op = "deprecate"
    elif c.op == "deprecate":
        new_op = "insert"
    else:  # update
        new_op = "update"
    return ChangeEntry(
        op=new_op,  # type: ignore[arg-type]
        kind=c.kind,
        id=c.id,
        before=c.after,
        after=c.before,
        source_ref_id=c.source_ref_id,
        actor=c.actor,
        ts=c.ts,
    )


def _apply_inverse(
    state: dict[str, dict[str, dict[str, Any]]], c: ChangeEntry
) -> None:
    """Mutate ``state`` to roll back the effect of ``c``."""
    bucket = state.setdefault(
        "entities" if c.kind == "entity" else "relations", {}
    )
    if c.op == "insert":
        bucket.pop(c.id, None)
    elif c.op == "deprecate":
        if c.before is not None:
            bucket[c.id] = c.before
    elif c.op == "update":
        if c.before is not None:
            bucket[c.id] = c.before
        else:
            bucket.pop(c.id, None)


def make_change(
    *,
    op: str,
    kind: str,
    id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    source_ref_id: str | None = None,
    actor: str | None = None,
) -> ChangeEntry:
    """Helper: build a ChangeEntry with the current UTC timestamp."""
    return ChangeEntry(
        op=op,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        id=id,
        before=before,
        after=after,
        source_ref_id=source_ref_id,
        actor=actor,
        ts=datetime.now(UTC),
    )


# Bookkeeping helpers — primarily for tests.
def group_by_kind(entries: list[ChangeEntry]) -> dict[str, list[ChangeEntry]]:
    out: dict[str, list[ChangeEntry]] = defaultdict(list)
    for e in entries:
        out[e.kind].append(e)
    return dict(out)
