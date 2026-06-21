"""Tests for ``GET /runs`` and ``GET /runs/{sv_id}`` — the SubjectVersion
log endpoints that power the refactored ``/runs`` page in the web app.

These endpoints sit on the same router as the rest of /industry_graph,
share the same singleton stores, and project each row with subject
context joined inline. We test the join, the filters, the sort order,
and the 404 path on the detail endpoint.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from shinkai_api.api import industry_graph as ig_router
from shinkai_api.industry_graph import IndustryGraphStore
from shinkai_api.industry_graph.subjects import (
    Subject,
    SubjectStore,
    SubjectVersion,
)
from shinkai_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    # Point the singleton stores at a tmp root so the real .shinkai
    # data doesn't leak in.
    ig_router._store = None
    ig_router._subject_store = None
    graph = IndustryGraphStore(root=tmp_path)
    asyncio.run(graph.load())
    ig_router._store = graph
    ss = SubjectStore(fs=graph.fs)
    asyncio.run(ss.load())
    ig_router._subject_store = ss

    # Seed: two Subjects, four SubjectVersions across them with varying
    # status + timing.
    async def seed() -> None:
        now = datetime.now(UTC)
        nvda = Subject(
            id="subj:nvda",
            type="company",
            display_name="NVIDIA",
            target_entity_id="co:NVDA",
            created_at=now,
            updated_at=now,
        )
        aapl = Subject(
            id="subj:aapl",
            type="company",
            display_name="Apple",
            target_entity_id="co:AAPL",
            created_at=now,
            updated_at=now,
        )
        await ss.upsert_subject(nvda)
        await ss.upsert_subject(aapl)

        # NVDA v1 (oldest, migration baseline), v2 (manual, completed),
        # v3 (running, no ended_at).
        nvda_v1 = SubjectVersion(
            id="sv:nvda:1",
            subject_id="subj:nvda",
            version_no=1,
            run_id="seed",
            snapshot_from=2,
            snapshot_to=2,
            triggered_by="migration",
            status="completed",
            started_at=now - timedelta(hours=10),
            ended_at=now - timedelta(hours=10),
        )
        nvda_v2 = SubjectVersion(
            id="sv:nvda:2",
            subject_id="subj:nvda",
            version_no=2,
            run_id="r2",
            snapshot_from=2,
            snapshot_to=3,
            triggered_by="manual",
            status="completed",
            started_at=now - timedelta(hours=2),
            ended_at=now - timedelta(hours=2),
        )
        nvda_v3 = SubjectVersion(
            id="sv:nvda:3",
            subject_id="subj:nvda",
            version_no=3,
            run_id="r3",
            snapshot_from=3,
            snapshot_to=3,
            triggered_by="manual",
            status="running",
            started_at=now - timedelta(minutes=5),
        )
        # AAPL v1 — only the migration baseline, sits in the middle of NVDA's
        # timeline by ended_at.
        aapl_v1 = SubjectVersion(
            id="sv:aapl:1",
            subject_id="subj:aapl",
            version_no=1,
            run_id="seed",
            snapshot_from=2,
            snapshot_to=2,
            triggered_by="migration",
            status="completed",
            started_at=now - timedelta(hours=6),
            ended_at=now - timedelta(hours=6),
        )
        for sv in (nvda_v1, nvda_v2, nvda_v3, aapl_v1):
            await ss.upsert_version(sv)

    asyncio.run(seed())
    return TestClient(create_app())


def test_list_runs_returns_all_versions_sorted_newest_first(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4
    rows = data["rows"]
    assert len(rows) == 4
    # Order: nvda v3 (running, started 5m ago) → nvda v2 (2h) →
    # aapl v1 (6h) → nvda v1 (10h)
    ids = [r["id"] for r in rows]
    assert ids == ["sv:nvda:3", "sv:nvda:2", "sv:aapl:1", "sv:nvda:1"]


def test_list_runs_joins_subject_context_onto_each_row(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs")
    row = r.json()["rows"][0]
    assert row["subject_id"] == "subj:nvda"
    assert row["subject_display_name"] == "NVIDIA"
    assert row["subject_type"] == "company"
    assert row["target_entity_id"] == "co:NVDA"


def test_list_runs_filter_by_subject(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs?subject_id=subj:aapl")
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["id"] == "sv:aapl:1"


def test_list_runs_filter_by_status(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs?status=running")
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["id"] == "sv:nvda:3"
    assert rows[0]["status"] == "running"


def test_list_runs_limit_caps_output(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs?limit=2")
    data = r.json()
    assert data["total"] == 4  # total reflects full match before limit
    assert len(data["rows"]) == 2
    assert data["count"] == 2


def test_get_run_returns_enriched_detail(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs/sv:nvda:2")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "sv:nvda:2"
    assert body["subject_display_name"] == "NVIDIA"
    assert body["subject_type"] == "company"
    assert body["target_entity_id"] == "co:NVDA"
    assert body["status"] == "completed"


def test_get_run_404_on_missing(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/api/v1/industry_graph/runs/sv:does-not-exist:1")
    assert r.status_code == 404
