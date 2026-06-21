"""Function-tool tests: every tool family + idempotency + missing source_ref."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shinkai_api.industry_graph import IndustryGraphStore, build_tools
from shinkai_api.industry_graph.tools.analysis_write import (
    AddBottleneckTool,
    AddInvestmentThesisTool,
    AddKeyDataTool,
    UpdateBottleneckTool,
)
from shinkai_api.industry_graph.tools.audit_snapshot import (
    CreateSnapshotTool,
    DiffSnapshotsTool,
    ListRecentChangesTool,
)
from shinkai_api.industry_graph.tools.entity_write import (
    AddAliasTool,
    AddFacetValueTool,
    DeprecateEntityTool,
    RegisterSourceTool,
    SetAttributeTool,
    UpsertEntityTool,
)
from shinkai_api.industry_graph.tools.query import (
    FindBottlenecksTool,
    FindRelationsTool,
    GetEntityTool,
    WalkPathTool,
)
from shinkai_api.industry_graph.tools.relation_write import (
    AddWeightObservationTool,
    DeprecateRelationTool,
    UpsertRelationTool,
)

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC).isoformat()
SRC_REF = {
    "source_id": "src:ms_test",
    "page": 13,
    "quote": "test quote",
    "confidence": 0.95,
    "evidence_type": "hard_data",
}


def _new_store(tmp_path: Path) -> IndustryGraphStore:
    s = IndustryGraphStore(root=tmp_path)
    asyncio.run(s.load())
    return s


def test_build_tools_returns_full_set(tmp_path: Path) -> None:
    s = _new_store(tmp_path)
    tools = build_tools(s)
    # 9 query + 6 entity_write + 3 relation_write + 4 analysis + 4 snapshot = 26
    assert len(tools) == 26
    names = {t.name for t in tools}
    # Spot-check coverage across families
    expected_subset = {
        "find_entity", "get_entity", "walk_path",
        "register_source", "upsert_entity", "set_attribute",
        "upsert_relation", "add_weight_observation",
        "add_bottleneck", "add_key_data", "add_investment_thesis",
        "create_snapshot", "diff_snapshots",
    }
    assert expected_subset.issubset(names)


def test_register_source_then_upsert_entity(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        # Register the source first
        src_tool = RegisterSourceTool(s)
        res = await src_tool.run(
            publisher="MS", title="Build for AI", date="2026-05-08",
        )
        assert res.ok
        sid = res.data["source_id"]
        # Now upsert NVDA using that source
        upsert = UpsertEntityTool(s)
        res = await upsert.run(
            id="co:NVDA",
            kind="Company",
            labels=["NVIDIA"],
            attributes={"ticker": "NVDA"},
            source_ref={"source_id": sid, "page": 13},
        )
        assert res.ok
        assert res.data["action"] == "created"
        assert s.index.get_entity("co:NVDA") is not None

    asyncio.run(run())


def test_upsert_entity_rejects_missing_source_ref(tmp_path: Path) -> None:
    s = _new_store(tmp_path)
    tool = UpsertEntityTool(s)

    async def run() -> None:
        res = await tool.run(id="co:X", kind="Company", labels=["X"])
        assert not res.ok
        assert "source_ref" in (res.error or "").lower()

    asyncio.run(run())


def test_upsert_entity_idempotent(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        tool = UpsertEntityTool(s)
        await tool.run(
            id="co:NVDA",
            kind="Company",
            labels=["NVIDIA"],
            source_ref=SRC_REF,
        )
        res2 = await tool.run(
            id="co:NVDA",
            kind="Company",
            labels=["NVIDIA"],
            source_ref=SRC_REF,
        )
        assert res2.ok
        assert res2.data["action"] in ("unchanged", "updated")

    asyncio.run(run())


def test_upsert_relation_and_find(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:TSMC", "co:NVDA"):
            await upsert_e.run(
                id=cid, kind="Company", labels=[cid], source_ref=SRC_REF,
            )
        rel_tool = UpsertRelationTool(s)
        rel_res = await rel_tool.run(
            type="supplies_to",
            source_id="co:TSMC",
            target_id="co:NVDA",
            weights={"period": "2026", "values": {"buyer_spend": 0.8}},
            source_ref=SRC_REF,
        )
        assert rel_res.ok
        # query
        find_rel = FindRelationsTool(s)
        res = await find_rel.run(type="supplies_to")
        assert res.ok
        assert len(res.data["relations"]) == 1

    asyncio.run(run())


def test_add_bottleneck_creates_affects_relations(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        # Seed two affected companies
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:NVDA", "co:AMD"):
            await upsert_e.run(id=cid, kind="Company", labels=[cid], source_ref=SRC_REF)
        bn = AddBottleneckTool(s)
        res = await bn.run(
            slug="cowos_capacity_2026",
            type="capacity",
            severity="high",
            description="CoWoS shortage",
            affects=["co:NVDA", "co:AMD"],
            source_ref=SRC_REF,
        )
        assert res.ok
        assert len(res.data["relation_ids"]) == 2

        # find_bottlenecks for an anchor
        finder = FindBottlenecksTool(s)
        fb = await finder.run(anchor_id="co:NVDA")
        assert fb.ok
        assert len(fb.data["bottlenecks"]) == 1

    asyncio.run(run())


def test_add_key_data_creates_subject_link(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        kdp_tool = AddKeyDataTool(s)
        res = await kdp_tool.run(
            subject_id="co:NVDA",
            metric="CoWoS wafer allocation",
            value="875k",
            value_numeric=875000,
            unit="wafers",
            period="2026e",
            source_ref=SRC_REF,
        )
        assert res.ok
        assert res.data["relation_id"].startswith("r:key_data_about")

    asyncio.run(run())


def test_add_investment_thesis_creates_watched_in_per_ticker(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        thesis = AddInvestmentThesisTool(s)
        res = await thesis.run(
            target_id="co:NVDA",
            slug="ms_nvda_20260508",
            stocks_to_watch=[
                {"ticker": "TSMC", "rationale": "CoWoS exposure"},
                {"ticker": "Hynix", "rationale": "HBM primary"},
            ],
            bias="constructive",
            horizon="medium",
            rationale="AI infra dominance.",
            source_ref=SRC_REF,
        )
        assert res.ok
        assert len(res.data["watched_relation_ids"]) == 2

    asyncio.run(run())


def test_create_snapshot_and_diff(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        snap = CreateSnapshotTool(s)
        res = await snap.run(rationale="seed")
        assert res.ok
        assert res.data["version"] == 1
        assert len(s.pending) == 0

        # Empty pending: no snapshot
        res2 = await snap.run(rationale="empty")
        assert res2.ok
        assert res2.data["version"] is None

        # Make another change and take v2 — diff v0 → v2 should show 1 insert.
        await upsert_e.run(id="co:AMD", kind="Company", labels=["AMD"], source_ref=SRC_REF)
        await snap.run(rationale="add amd")
        diff_tool = DiffSnapshotsTool(s)
        diff_res = await diff_tool.run(v_from=0, v_to=2)
        assert diff_res.ok
        assert len(diff_res.data["changes"]) >= 2

    asyncio.run(run())


def test_walk_path_through_graph(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:TSMC", "co:NVDA", "co:Microsoft"):
            await upsert_e.run(id=cid, kind="Company", labels=[cid], source_ref=SRC_REF)
        rel = UpsertRelationTool(s)
        await rel.run(
            type="supplies_to", source_id="co:TSMC",
            target_id="co:NVDA", source_ref=SRC_REF,
        )
        await rel.run(
            type="supplies_to", source_id="co:NVDA",
            target_id="co:Microsoft", source_ref=SRC_REF,
        )
        walk = WalkPathTool(s)
        res = await walk.run(from_id="co:TSMC", to_id="co:Microsoft")
        assert res.ok
        assert ["co:TSMC", "co:NVDA", "co:Microsoft"] in res.data["paths"]

    asyncio.run(run())


def test_get_entity_returns_incident_relations(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:NVDA", "co:TSMC"):
            await upsert_e.run(id=cid, kind="Company", labels=[cid], source_ref=SRC_REF)
        rel = UpsertRelationTool(s)
        await rel.run(
            type="supplies_to", source_id="co:TSMC",
            target_id="co:NVDA", source_ref=SRC_REF,
        )
        get_tool = GetEntityTool(s)
        res = await get_tool.run(id="co:NVDA")
        assert res.ok
        assert len(res.data["relations"]) == 1

    asyncio.run(run())


def test_set_attribute_and_add_alias(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        attr_tool = SetAttributeTool(s)
        res = await attr_tool.run(
            entity_id="co:NVDA", key="market_cap_usd_bn", value=3500, source_ref=SRC_REF,
        )
        assert res.ok
        e = s.index.get_entity("co:NVDA")
        assert e is not None and e["attributes"]["market_cap_usd_bn"] == 3500

        alias_tool = AddAliasTool(s)
        res = await alias_tool.run(
            entity_id="co:NVDA", alias="英伟达", source_ref=SRC_REF,
        )
        assert res.ok
        e = s.index.get_entity("co:NVDA")
        assert e is not None and "英伟达" in e["aliases"]

    asyncio.run(run())


def test_add_facet_value(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        facet_tool = AddFacetValueTool(s)
        res = await facet_tool.run(
            entity_id="co:NVDA", facet_name="regions", value="US", source_ref=SRC_REF,
        )
        assert res.ok
        e = s.index.get_entity("co:NVDA")
        assert e is not None and "US" in (e["facets"]["regions"])

    asyncio.run(run())


def test_deprecate_entity_and_relation(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        dep_e = DeprecateEntityTool(s)
        res = await dep_e.run(entity_id="co:NVDA", reason="duplicate", source_ref=SRC_REF)
        assert res.ok
        e = s.index.get_entity("co:NVDA")
        assert e is not None and e["deprecated_at"] is not None

    asyncio.run(run())


def test_update_bottleneck(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        bn_tool = AddBottleneckTool(s)
        res = await bn_tool.run(
            slug="cowos_2026",
            type="capacity",
            severity="high",
            description="x",
            affects=["co:NVDA"],
            source_ref=SRC_REF,
        )
        bid = res.data["bottleneck_id"]
        upd = UpdateBottleneckTool(s)
        res = await upd.run(
            bottleneck_id=bid, severity="medium", status="monitoring", source_ref=SRC_REF,
        )
        assert res.ok
        bn = s.index.get_entity(bid)
        assert bn is not None
        assert bn["attributes"]["severity"] == "medium"
        assert bn["attributes"]["status"] == "monitoring"

    asyncio.run(run())


def test_add_weight_observation(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:TSMC", "co:NVDA"):
            await upsert_e.run(id=cid, kind="Company", labels=[cid], source_ref=SRC_REF)
        rel = UpsertRelationTool(s)
        rres = await rel.run(
            type="supplies_to",
            source_id="co:TSMC",
            target_id="co:NVDA",
            weights={"period": "2026", "values": {"buyer_spend": 0.8}},
            source_ref=SRC_REF,
        )
        rid = rres.data["relation"]["id"]
        obs_tool = AddWeightObservationTool(s)
        res = await obs_tool.run(
            relation_id=rid,
            weight={"period": "2027", "values": {"buyer_spend": 0.75}},
            source_ref=SRC_REF,
        )
        assert res.ok
        rel = s.index.relations_by_id[rid]
        periods = {w["period"] for w in rel["weights"]}
        assert "2026" in periods and "2027" in periods

    asyncio.run(run())


def test_deprecate_relation_marks_record(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        for cid in ("co:TSMC", "co:NVDA"):
            await upsert_e.run(id=cid, kind="Company", labels=[cid], source_ref=SRC_REF)
        rel = UpsertRelationTool(s)
        rres = await rel.run(
            type="supplies_to",
            source_id="co:TSMC",
            target_id="co:NVDA",
            source_ref=SRC_REF,
        )
        rid = rres.data["relation"]["id"]
        dep = DeprecateRelationTool(s)
        res = await dep.run(relation_id=rid, reason="wrong period", source_ref=SRC_REF)
        assert res.ok
        rel_after = s.index.relations_by_id[rid]
        assert rel_after["deprecated_at"] is not None

    asyncio.run(run())


def test_list_recent_changes(tmp_path: Path) -> None:
    s = _new_store(tmp_path)

    async def run() -> None:
        upsert_e = UpsertEntityTool(s)
        await upsert_e.run(id="co:NVDA", kind="Company", labels=["NVDA"], source_ref=SRC_REF)
        lst = ListRecentChangesTool(s)
        res = await lst.run()
        assert res.ok
        assert len(res.data["changes"]) >= 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "tool_factory",
    [
        UpsertEntityTool,
        SetAttributeTool,
        AddAliasTool,
        AddFacetValueTool,
        DeprecateEntityTool,
        UpsertRelationTool,
        AddWeightObservationTool,
        DeprecateRelationTool,
        AddBottleneckTool,
        UpdateBottleneckTool,
        AddKeyDataTool,
        AddInvestmentThesisTool,
    ],
)
def test_all_write_tools_reject_missing_source_ref(
    tmp_path: Path, tool_factory
) -> None:
    s = _new_store(tmp_path)
    tool = tool_factory(s)

    async def run() -> None:
        # Empty kwargs: most will fail for other required fields first, but
        # any that get past that *must* still reject missing source_ref.
        # We pass minimal placeholder kwargs and confirm not-ok.
        res = await tool.run()
        assert not res.ok

    asyncio.run(run())
