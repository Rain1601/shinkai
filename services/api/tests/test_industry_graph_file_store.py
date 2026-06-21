"""File store tests: round-trip, atomicity, missing-shard tolerance."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from shinkai_api.industry_graph.store import IndustryGraphFileStore, paths


def _store(tmp_path: Path) -> IndustryGraphFileStore:
    return IndustryGraphFileStore(root=tmp_path)


def _nvda_payload() -> dict:
    return {
        "target": "NVDA",
        "entities": [
            {"id": "co:NVDA", "kind": "Company", "labels": ["NVIDIA"]},
        ],
        "relations": [
            {"id": "r:supplies_to~co_TSMC~co_NVDA~2026", "type": "supplies_to"},
        ],
    }


def test_target_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.persist_target("NVDA", _nvda_payload())
        got = await store.load_target("NVDA")
        assert got == _nvda_payload()

    asyncio.run(run())


def test_load_missing_target_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert asyncio.run(store.load_target("NONEXISTENT")) is None


def test_list_targets(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.persist_target("NVDA", _nvda_payload())
        await store.persist_target("AAPL", {"target": "AAPL"})
        targets = await store.list_targets()
        assert targets == ["AAPL", "NVDA"]

    asyncio.run(run())


def test_shared_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        payload = {"companies": [{"id": "co:TSMC"}]}
        await store.persist_shared("companies", payload)
        assert await store.load_shared("companies") == payload

    asyncio.run(run())


def test_manifest_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    m = {"current_version": 1, "targets": ["NVDA"]}
    asyncio.run(store.persist_manifest(m))
    assert asyncio.run(store.load_manifest()) == m


def test_snapshot_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meta = {"version": 1, "parent_version": None, "rationale": "init"}
    changes = [
        {"op": "insert", "kind": "entity", "id": "co:NVDA"},
        {"op": "insert", "kind": "entity", "id": "co:TSMC"},
    ]

    async def run() -> None:
        await store.persist_snapshot(version=1, meta=meta, changes=changes)
        assert await store.load_snapshot_meta(1) == meta
        assert await store.load_snapshot_changes(1) == changes

    asyncio.run(run())


def test_snapshot_list_versions(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.persist_snapshot(version=1, meta={"version": 1}, changes=[])
        await store.persist_snapshot(version=2, meta={"version": 2}, changes=[])
        await store.persist_snapshot(version=5, meta={"version": 5}, changes=[])
        versions = await store.list_snapshot_versions()
        assert versions == [1, 2, 5]

    asyncio.run(run())


def test_audit_append_and_read(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.append_audit({"op": "insert", "id": "co:NVDA"})
        await store.append_audit({"op": "update", "id": "co:TSMC"})
        entries = await store.read_audit()
        assert len(entries) == 2
        assert entries[0]["op"] == "insert"
        assert entries[1]["op"] == "update"
        assert "ts" in entries[0]

    asyncio.run(run())


def test_atomic_write_no_leftover_tmp(tmp_path: Path) -> None:
    """No partial file is left behind after a write."""
    store = _store(tmp_path)
    asyncio.run(store.persist_target("NVDA", _nvda_payload()))
    target_dir = paths.targets_dir(store.root)
    leftover_tmp = list(target_dir.glob("*.tmp"))
    assert leftover_tmp == []


def test_concurrent_writes_serialize(tmp_path: Path) -> None:
    """Many concurrent writes to different shards all land cleanly."""
    store = _store(tmp_path)

    async def run() -> None:
        async def write_one(i: int) -> None:
            await store.persist_target(f"T{i:02d}", {"target": f"T{i:02d}"})

        await asyncio.gather(*[write_one(i) for i in range(20)])
        targets = await store.list_targets()
        assert len(targets) == 20

    asyncio.run(run())


def test_corrupt_json_raises_clear_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    paths.targets_dir(store.root).mkdir(parents=True, exist_ok=True)
    bad = paths.target_shard_path(store.root, "BROKEN")
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Corrupt JSON"):
        asyncio.run(store.load_target("BROKEN"))


def test_path_resolution_default() -> None:
    """Default root respects env override."""
    saved = os.environ.pop("SHINKAI_INDUSTRY_GRAPH_PATH", None)
    try:
        assert paths.resolve_root() == paths.DEFAULT_ROOT
        os.environ["SHINKAI_INDUSTRY_GRAPH_PATH"] = "/tmp/override"
        assert paths.resolve_root() == Path("/tmp/override")
    finally:
        if saved is not None:
            os.environ["SHINKAI_INDUSTRY_GRAPH_PATH"] = saved
        else:
            os.environ.pop("SHINKAI_INDUSTRY_GRAPH_PATH", None)


def test_path_helpers() -> None:
    root = Path("/tmp/ig")
    assert paths.manifest_path(root) == Path("/tmp/ig/manifest.json")
    assert paths.target_shard_path(root, "NVDA") == Path(
        "/tmp/ig/current/targets/NVDA.json"
    )
    assert paths.shared_shard_path(root, "companies") == Path(
        "/tmp/ig/current/shared/companies.json"
    )
    assert paths.snapshot_meta_path(root, 7) == Path(
        "/tmp/ig/snapshots/v0007/meta.json"
    )


def test_persist_target_writes_real_file(tmp_path: Path) -> None:
    """Sanity check: the file actually appears with correct content."""
    store = IndustryGraphFileStore(root=tmp_path)
    asyncio.run(store.persist_target("NVDA", _nvda_payload()))
    path = paths.target_shard_path(tmp_path, "NVDA")
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == _nvda_payload()
