"""SnapshotManager tests: commit, diff symmetry, reconstruction."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shinkai_api.industry_graph.store import (
    IndustryGraphFileStore,
    SnapshotManager,
    make_change,
)


def _store(tmp_path: Path) -> SnapshotManager:
    fs = IndustryGraphFileStore(root=tmp_path)
    return SnapshotManager(fs)


def test_commit_assigns_next_version(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        m1 = await mgr.commit(
            rationale="first",
            changes=[
                make_change(
                    op="insert",
                    kind="entity",
                    id="co:NVDA",
                    after={"id": "co:NVDA", "kind": "Company"},
                ),
            ],
        )
        assert m1.version == 1
        assert m1.parent_version is None

        m2 = await mgr.commit(
            rationale="second",
            changes=[
                make_change(
                    op="insert",
                    kind="entity",
                    id="co:TSMC",
                    after={"id": "co:TSMC", "kind": "Company"},
                ),
            ],
        )
        assert m2.version == 2
        assert m2.parent_version == 1

    asyncio.run(run())


def test_commit_summary_counts(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        meta = await mgr.commit(
            rationale="mix",
            changes=[
                make_change(op="insert", kind="entity", id="co:A", after={"kind": "Company"}),
                make_change(op="insert", kind="entity", id="co:B", after={"kind": "Company"}),
                make_change(op="insert", kind="entity", id="bn:1", after={"kind": "Bottleneck"}),
                make_change(op="insert", kind="entity", id="kdp:1", after={"kind": "KeyDataPoint"}),
                make_change(op="update", kind="entity", id="co:A", before={}, after={"k": 1}),
                make_change(op="insert", kind="relation", id="r:1", after={"type": "supplies_to"}),
                make_change(op="insert", kind="relation", id="r:2", after={"type": "supplies_to"}),
                make_change(op="deprecate", kind="relation", id="r:3", before={"type": "x"}),
            ],
        )
        s = meta.changeset_summary
        assert s.entities_added == 4
        assert s.entities_updated == 1
        assert s.relations_added == 2
        assert s.relations_deprecated == 1
        assert s.bottlenecks_added == 1
        assert s.key_data_added == 1

    asyncio.run(run())


def test_diff_forward(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        await mgr.commit(
            rationale="v1",
            changes=[make_change(op="insert", kind="entity", id="co:NVDA", after={})],
        )
        await mgr.commit(
            rationale="v2",
            changes=[make_change(op="insert", kind="entity", id="co:TSMC", after={})],
        )
        diff = await mgr.diff(0, 2)
        assert {c.id for c in diff} == {"co:NVDA", "co:TSMC"}
        assert all(c.op == "insert" for c in diff)

    asyncio.run(run())


def test_diff_reverse_inverts_ops(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        await mgr.commit(
            rationale="v1",
            changes=[make_change(op="insert", kind="entity", id="co:NVDA", after={"x": 1})],
        )
        await mgr.commit(
            rationale="v2",
            changes=[
                make_change(
                    op="update",
                    kind="entity",
                    id="co:NVDA",
                    before={"x": 1},
                    after={"x": 2},
                ),
            ],
        )
        # Reverse diff: 2 → 0 should undo both changes.
        reverse = await mgr.diff(2, 0)
        ops = [c.op for c in reverse]
        # update should swap before/after (still 'update'); insert becomes deprecate.
        assert "deprecate" in ops
        assert "update" in ops

    asyncio.run(run())


def test_reconstruct_to_earlier_version(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        await mgr.commit(
            rationale="v1",
            changes=[
                make_change(
                    op="insert",
                    kind="entity",
                    id="co:NVDA",
                    after={"id": "co:NVDA", "kind": "Company", "labels": ["NVIDIA"]},
                ),
            ],
        )
        await mgr.commit(
            rationale="v2",
            changes=[
                make_change(
                    op="insert",
                    kind="entity",
                    id="co:TSMC",
                    after={"id": "co:TSMC", "kind": "Company"},
                ),
                make_change(
                    op="update",
                    kind="entity",
                    id="co:NVDA",
                    before={"id": "co:NVDA", "kind": "Company", "labels": ["NVIDIA"]},
                    after={"id": "co:NVDA", "kind": "Company", "labels": ["NVIDIA Corp"]},
                ),
            ],
        )

        current = {
            "entities": {
                "co:NVDA": {"id": "co:NVDA", "kind": "Company", "labels": ["NVIDIA Corp"]},
                "co:TSMC": {"id": "co:TSMC", "kind": "Company"},
            },
            "relations": {},
        }

        # Roll back to v1: TSMC should disappear; NVDA labels revert.
        v1_state = await mgr.reconstruct_state(current, target_version=1)
        assert "co:TSMC" not in v1_state["entities"]
        assert v1_state["entities"]["co:NVDA"]["labels"] == ["NVIDIA"]

    asyncio.run(run())


def test_reconstruct_rejects_future_version(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        await mgr.commit(rationale="v1", changes=[])
        try:
            await mgr.reconstruct_state({}, target_version=5)
        except ValueError as e:
            assert "Target version" in str(e)
            return
        raise AssertionError("Expected ValueError")

    asyncio.run(run())


def test_load_meta_round_trip(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        m = await mgr.commit(
            rationale="hello",
            changes=[
                make_change(op="insert", kind="entity", id="co:NVDA", after={}),
            ],
            created_by_run_id="run_x",
        )
        loaded = await mgr.load_meta(m.version)
        assert loaded is not None
        assert loaded.rationale == "hello"
        assert loaded.created_by_run_id == "run_x"

    asyncio.run(run())


def test_load_changes_round_trip(tmp_path: Path) -> None:
    mgr = _store(tmp_path)

    async def run() -> None:
        ch = [
            make_change(op="insert", kind="entity", id="co:NVDA", after={"k": 1}),
            make_change(op="insert", kind="entity", id="co:TSMC", after={"k": 2}),
        ]
        await mgr.commit(rationale="x", changes=ch)
        loaded = await mgr.load_changes(1)
        assert len(loaded) == 2
        assert {c.id for c in loaded} == {"co:NVDA", "co:TSMC"}

    asyncio.run(run())
