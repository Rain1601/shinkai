"""Tests for the Subjects layer — schemas, store CRUD, per-subject run lock.

The store mirrors the file_store pattern used by entities/relations: sharded
JSON under ``current/shared/`` with atomic write semantics. The interesting
new bit is the per-subject asyncio run lock — these tests cover both the
happy path and the contention case.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from shinkai_api.industry_graph.store.file_store import IndustryGraphFileStore
from shinkai_api.industry_graph.subjects import (
    Subject,
    SubjectStore,
    SubjectVersion,
    SubjectVersionChangeSummary,
)
from shinkai_api.industry_graph.subjects.store import SubjectLockBusy


def _now() -> datetime:
    return datetime.now(UTC)


def _make_store(tmp_path: Path) -> SubjectStore:
    fs = IndustryGraphFileStore(root=tmp_path)
    s = SubjectStore(fs=fs)
    asyncio.run(s.load())
    return s


def _company_subject(slug: str = "nvda", target: str = "co:NVDA") -> Subject:
    now = _now()
    return Subject(
        id=f"subj:{slug}",
        type="company",
        display_name=slug.upper(),
        target_entity_id=target,
        created_at=now,
        updated_at=now,
    )


# ── schemas: round-trip + extra-allow ───────────────────────────────────
def test_subject_round_trip_json() -> None:
    s = _company_subject()
    j = s.model_dump(mode="json")
    rebuilt = Subject.model_validate(j)
    assert rebuilt == s


def test_subject_version_change_summary_nullable() -> None:
    """change_summary must be nullable — backfill v1 has no diff."""
    sv = SubjectVersion(
        id="sv:nvda:1",
        subject_id="subj:nvda",
        version_no=1,
        run_id="seed",
        snapshot_from=2,
        snapshot_to=2,
        triggered_by="migration",
        status="completed",
        started_at=_now(),
        ended_at=_now(),
        change_summary=None,
    )
    assert sv.change_summary is None
    j = sv.model_dump(mode="json")
    assert j["change_summary"] is None
    rebuilt = SubjectVersion.model_validate(j)
    assert rebuilt.change_summary is None


def test_subject_extra_fields_pass_through() -> None:
    s = _company_subject()
    raw = s.model_dump(mode="json")
    raw["notes"] = "extra"
    rebuilt = Subject.model_validate(raw)
    assert rebuilt.model_dump()["notes"] == "extra"


# ── store: CRUD ──────────────────────────────────────────────────────────
def test_upsert_and_list(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        a = _company_subject("nvda", "co:NVDA")
        b = _company_subject("aapl", "co:AAPL")
        await store.upsert_subject(a)
        await store.upsert_subject(b)
        rows = await store.list_subjects()
        ids = sorted(r.id for r in rows)
        assert ids == ["subj:aapl", "subj:nvda"]

    asyncio.run(run())


def test_upsert_subject_preserves_created_at_on_update(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        s = _company_subject()
        await store.upsert_subject(s)
        first = await store.get_subject(s.id)
        # Simulate an update with a different "claimed" created_at.
        bumped = s.model_copy(
            update={"display_name": "NVIDIA New Name", "created_at": _now()}
        )
        await store.upsert_subject(bumped)
        after = await store.get_subject(s.id)
        assert after is not None and first is not None
        assert after.created_at == first.created_at  # not clobbered
        assert after.display_name == "NVIDIA New Name"
        assert after.updated_at >= first.updated_at

    asyncio.run(run())


def test_versions_listed_oldest_first(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        for vn in [3, 1, 2]:
            await store.upsert_version(
                SubjectVersion(
                    id=f"sv:nvda:{vn}",
                    subject_id="subj:nvda",
                    version_no=vn,
                    run_id=f"r{vn}",
                    snapshot_from=vn,
                    snapshot_to=vn,
                    triggered_by="manual",
                    status="completed",
                    started_at=_now(),
                )
            )
        rows = await store.list_versions("subj:nvda")
        assert [r.version_no for r in rows] == [1, 2, 3]

    asyncio.run(run())


def test_latest_and_next_version_no(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        assert await store.latest_version_no("subj:nvda") == 0
        assert await store.next_version_no("subj:nvda") == 1
        await store.upsert_version(
            SubjectVersion(
                id="sv:nvda:1",
                subject_id="subj:nvda",
                version_no=1,
                run_id="r1",
                snapshot_from=1,
                snapshot_to=1,
                triggered_by="manual",
                status="completed",
                started_at=_now(),
            )
        )
        assert await store.latest_version_no("subj:nvda") == 1
        assert await store.next_version_no("subj:nvda") == 2
        # Different subject — independent counter.
        assert await store.next_version_no("subj:aapl") == 1

    asyncio.run(run())


def test_update_version_status_persists(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        await store.upsert_version(
            SubjectVersion(
                id="sv:nvda:1",
                subject_id="subj:nvda",
                version_no=1,
                run_id="r1",
                snapshot_from=2,
                snapshot_to=2,
                triggered_by="manual",
                status="running",
                started_at=_now(),
            )
        )
        ended = _now()
        updated = await store.update_version_status(
            "sv:nvda:1", status="completed", ended_at=ended
        )
        assert updated.status == "completed"
        # Re-read from a fresh store to confirm the persistence round-tripped.
        fresh = SubjectStore(fs=IndustryGraphFileStore(root=store.root))
        await fresh.load()
        row = await fresh.get_version("sv:nvda:1")
        assert row is not None
        assert row.status == "completed"
        assert row.ended_at is not None

    asyncio.run(run())


def test_change_summary_round_trip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def run() -> None:
        cs = SubjectVersionChangeSummary(
            entities_added=2,
            relations_added=1,
            highlights=["+ SK Innovation (battery)", "+ supplies_to → Tesla"],
        )
        await store.upsert_version(
            SubjectVersion(
                id="sv:nvda:2",
                subject_id="subj:nvda",
                version_no=2,
                run_id="r2",
                snapshot_from=2,
                snapshot_to=3,
                triggered_by="manual",
                status="completed",
                started_at=_now(),
                ended_at=_now(),
                change_summary=cs,
            )
        )
        fresh = SubjectStore(fs=IndustryGraphFileStore(root=store.root))
        await fresh.load()
        row = await fresh.get_version("sv:nvda:2")
        assert row is not None and row.change_summary is not None
        assert row.change_summary.entities_added == 2
        assert "+ SK Innovation (battery)" in row.change_summary.highlights

    asyncio.run(run())


# ── per-subject run lock ─────────────────────────────────────────────────
def test_run_lock_serializes_within_subject(tmp_path: Path) -> None:
    """Two parallel runs on the same Subject: second one raises SubjectLockBusy."""
    store = _make_store(tmp_path)

    async def run() -> None:
        sid = "subj:nvda"
        async with store.run_lock(sid):
            # While the first lock is held, a second non-blocking acquire must fail.
            try:
                async with store.run_lock(sid):
                    raise AssertionError("Second lock should not have been granted")
            except SubjectLockBusy as e:
                assert sid in str(e)
            # And the in-flight check must say True.
            assert store.is_run_in_flight(sid) is True
        # Released → the next acquire succeeds.
        assert store.is_run_in_flight(sid) is False
        async with store.run_lock(sid):
            pass

    asyncio.run(run())


def test_backfill_subjects_is_idempotent(tmp_path: Path) -> None:
    """Running the migration twice creates each Subject exactly once."""
    import os
    import subprocess

    # Use the real seed so the test exercises the discovery logic end-to-end.
    seed_path = Path(
        "/Users/rain/ResearchGraph/data/sop_v1/supply_chain_graph.json"
    )
    if not seed_path.exists():
        import pytest
        pytest.skip("seed file unavailable in this environment")

    root = tmp_path / "ig"
    env = os.environ.copy()
    env["SHINKAI_INDUSTRY_GRAPH_PATH"] = str(root)
    repo = Path(__file__).resolve().parent.parent

    # Seed the store first.
    seed_cmd = [
        "uv", "run", "python", "scripts/ingest_supply_chain_graph_seed.py",
        str(seed_path),
    ]
    r = subprocess.run(seed_cmd, cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    backfill = [
        "uv", "run", "python", "scripts/backfill_subjects.py",
    ]
    first = subprocess.run(backfill, cwd=repo, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(backfill, cwd=repo, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr

    # The second run must skip everything.
    assert "Created 0 subjects" in second.stdout
    assert "skipped" in second.stdout

    async def run_check() -> None:
        from shinkai_api.industry_graph.store.file_store import IndustryGraphFileStore
        fs = IndustryGraphFileStore(root=root)
        s = SubjectStore(fs=fs)
        await s.load()
        rows = await s.list_subjects()
        assert len(rows) >= 11  # at least the 11 high-degree companies
        # Every subject must have a v1 SubjectVersion.
        for subj in rows:
            versions = await s.list_versions(subj.id)
            assert len(versions) == 1
            assert versions[0].version_no == 1
            assert versions[0].triggered_by == "migration"
            assert versions[0].status == "completed"
            assert versions[0].change_summary is None

    asyncio.run(run_check())


def test_run_lock_isolated_per_subject(tmp_path: Path) -> None:
    """Different Subjects share NO locking."""
    store = _make_store(tmp_path)

    async def run() -> None:
        async with store.run_lock("subj:nvda"):
            # A different subject's lock must still be free.
            async with store.run_lock("subj:aapl"):
                pass
            assert store.is_run_in_flight("subj:aapl") is False

    asyncio.run(run())


# ── orchestrator ──────────────────────────────────────────────────────────
def test_orchestrator_writes_completed_version_with_scope(tmp_path: Path) -> None:
    """run_subject_analysis: pending row → AgentLoop → completed row with
    scope_node_ids harvested from the agent's tool results."""
    from shinkai_api.industry_graph import IndustryGraphStore
    from shinkai_api.industry_graph.subjects import run_subject_analysis

    async def run() -> None:
        graph = IndustryGraphStore(root=tmp_path)
        await graph.load()
        ss = SubjectStore(fs=graph.fs)
        await ss.load()

        subj = _company_subject("nvda", "co:NVDA")
        await ss.upsert_subject(subj)

        # Fake agent that simulates 3 tool calls touching three ids.
        async def fake_agent(**kw) -> dict:
            return {
                "session_id": kw["run_id"],
                "task": kw["task"],
                "turns_used": 3,
                "done_summary": "exploration only",
                "started_at": "2026-06-21T00:00:00+00:00",
                "finished_at": "2026-06-21T00:01:00+00:00",
                "actions": [],
                "touched_ids": ["co:NVDA", "co:AMD", "co:TSMC", "r:supplies_to~co:TSMC~co:NVDA"],
                "store_stats": {},
            }

        final = await run_subject_analysis(
            subject=subj,
            subject_store=ss,
            graph_store=graph,
            client=None,  # type: ignore[arg-type]
            agent_factory=fake_agent,
        )
        assert final.status == "completed"
        # version 1 since no migration v1
        assert final.version_no == 1
        # scope excludes relation ids, includes the three entities.
        assert "co:NVDA" in final.scope_node_ids
        assert "co:AMD" in final.scope_node_ids
        assert not any(s.startswith("r:") for s in final.scope_node_ids)
        # change_summary is computed but should be a no-op SubjectVersionChangeSummary
        # (no new snapshots were created).
        assert final.change_summary is not None
        assert final.change_summary.entities_added == 0
        # Persisted row reflects the same.
        from shinkai_api.industry_graph.store.file_store import IndustryGraphFileStore
        fresh = SubjectStore(fs=IndustryGraphFileStore(root=tmp_path))
        await fresh.load()
        row = await fresh.get_version(final.id)
        assert row is not None and row.status == "completed"

    asyncio.run(run())


def test_orchestrator_failure_persists_failed_status(tmp_path: Path) -> None:
    from shinkai_api.industry_graph import IndustryGraphStore
    from shinkai_api.industry_graph.subjects import run_subject_analysis

    async def run() -> None:
        graph = IndustryGraphStore(root=tmp_path)
        await graph.load()
        ss = SubjectStore(fs=graph.fs)
        await ss.load()
        subj = _company_subject("aapl", "co:AAPL")
        await ss.upsert_subject(subj)

        async def angry_agent(**kw) -> dict:
            raise RuntimeError("LLM is having a bad day")

        try:
            await run_subject_analysis(
                subject=subj,
                subject_store=ss,
                graph_store=graph,
                client=None,  # type: ignore[arg-type]
                agent_factory=angry_agent,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("orchestrator should have re-raised")

        rows = await ss.list_versions(subj.id)
        assert len(rows) == 1 and rows[0].status == "failed"
        assert rows[0].error and "bad day" in rows[0].error

    asyncio.run(run())


def test_orchestrator_serializes_concurrent_runs(tmp_path: Path) -> None:
    """Two concurrent run_subject_analysis calls: the second must raise
    SubjectLockBusy without starting."""
    from shinkai_api.industry_graph import IndustryGraphStore
    from shinkai_api.industry_graph.subjects import (
        SubjectLockBusy,
        run_subject_analysis,
    )

    async def run() -> None:
        graph = IndustryGraphStore(root=tmp_path)
        await graph.load()
        ss = SubjectStore(fs=graph.fs)
        await ss.load()
        subj = _company_subject("nvda", "co:NVDA")
        await ss.upsert_subject(subj)

        slow_started = asyncio.Event()
        slow_release = asyncio.Event()

        async def slow_agent(**kw) -> dict:
            slow_started.set()
            await slow_release.wait()
            return {
                "session_id": kw["run_id"], "task": kw["task"], "turns_used": 1,
                "done_summary": "slow", "started_at": "", "finished_at": "",
                "actions": [], "touched_ids": ["co:NVDA"], "store_stats": {},
            }

        first = asyncio.create_task(run_subject_analysis(
            subject=subj, subject_store=ss, graph_store=graph,
            client=None, agent_factory=slow_agent,  # type: ignore[arg-type]
        ))
        await slow_started.wait()  # first run is now inside the lock

        # Second concurrent attempt should bail out.
        async def fast_agent(**kw) -> dict:  # pragma: no cover - never called
            raise AssertionError("second run must not start")

        try:
            await run_subject_analysis(
                subject=subj, subject_store=ss, graph_store=graph,
                client=None, agent_factory=fast_agent,  # type: ignore[arg-type]
            )
        except SubjectLockBusy:
            pass
        else:
            raise AssertionError("expected SubjectLockBusy")

        slow_release.set()
        result = await first
        assert result.status == "completed"

    asyncio.run(run())
