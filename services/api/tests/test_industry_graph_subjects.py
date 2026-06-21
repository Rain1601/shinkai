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
