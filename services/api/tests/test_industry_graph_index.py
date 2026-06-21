"""In-memory index tests: build, query, mutate, walk."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shinkai_api.industry_graph.schemas import (
    EntityBase,
    FacetSet,
    RelationBase,
    WeightCell,
    company_id,
    relation_id,
)
from shinkai_api.industry_graph.store import IndexLayer

_NOW = datetime(2026, 6, 21, tzinfo=UTC)


def _company(
    eid: str,
    *,
    ticker: str | None = None,
    sectors=("Semiconductor",),
    regions=("US",),
) -> EntityBase:
    attrs = {"ticker": ticker} if ticker else {}
    return EntityBase(
        id=eid,
        kind="Company",
        labels=[eid.split(":", 1)[-1]],
        attributes=attrs,
        facets=FacetSet(sectors=list(sectors), regions=list(regions)),
        created_at=_NOW,
        updated_at=_NOW,
    )


def _supplies(src: str, tgt: str, *, period: str = "2026") -> RelationBase:
    return RelationBase(
        id=relation_id("supplies_to", src, tgt, period),
        type="supplies_to",
        source_id=src,
        target_id=tgt,
        weights=[WeightCell(period=period, values={"buyer_spend": 0.8})],
        created_at=_NOW,
        updated_at=_NOW,
    )


def _competes(a: str, b: str) -> RelationBase:
    return RelationBase(
        id=relation_id("competes_with", a, b),
        type="competes_with",
        source_id=a,
        target_id=b,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_add_entity_indexes_by_kind_ticker_facet() -> None:
    idx = IndexLayer()
    idx.add_entity(_company("co:NVDA", ticker="NVDA"))

    assert idx.get_entity("co:NVDA") is not None
    assert idx.find_by_ticker("NVDA")["id"] == "co:NVDA"
    assert [e["id"] for e in idx.list_by_kind("Company")] == ["co:NVDA"]
    assert [e["id"] for e in idx.list_by_facet("sectors", "Semiconductor")] == ["co:NVDA"]
    assert [e["id"] for e in idx.list_by_facet("regions", "US")] == ["co:NVDA"]


def test_add_relation_updates_buckets_and_graph() -> None:
    idx = IndexLayer()
    idx.add_entity(_company("co:TSMC", ticker="TSMC"))
    idx.add_entity(_company("co:NVDA", ticker="NVDA"))
    rel = _supplies("co:TSMC", "co:NVDA")
    idx.add_relation(rel)

    assert idx.relations_by_id[rel.id]["type"] == "supplies_to"
    assert rel.id in idx.relations_by_source["co:TSMC"]
    assert rel.id in idx.relations_by_target["co:NVDA"]
    assert rel.id in idx.relations_by_type["supplies_to"]
    assert idx.graph.has_edge("co:TSMC", "co:NVDA", key=rel.id)


def test_relations_for_directional_filter() -> None:
    idx = IndexLayer()
    idx.bulk_load(
        entities=[_company(company_id(t)) for t in ("NVDA", "TSMC", "Microsoft")],
        relations=[
            _supplies(company_id("TSMC"), company_id("NVDA")),
            _supplies(company_id("NVDA"), company_id("Microsoft")),
            _competes(company_id("NVDA"), company_id("TSMC")),
        ],
    )

    out_rels = idx.relations_for(company_id("NVDA"), direction="out")
    in_rels = idx.relations_for(company_id("NVDA"), direction="in")
    only_supplies = idx.relations_for(company_id("NVDA"), type="supplies_to")

    assert {r["target_id"] for r in out_rels} == {company_id("Microsoft"), company_id("TSMC")}
    # "competes_with" went NVDA → TSMC so it's outgoing, not incoming.
    assert {r["source_id"] for r in in_rels} == {company_id("TSMC")}
    # supplies_to in either direction touching NVDA.
    assert {r["id"] for r in only_supplies} == {
        relation_id("supplies_to", company_id("TSMC"), company_id("NVDA"), "2026"),
        relation_id("supplies_to", company_id("NVDA"), company_id("Microsoft"), "2026"),
    }


def test_walk_paths_basic() -> None:
    idx = IndexLayer()
    nvda, tsmc, hynix = company_id("NVDA"), company_id("TSMC"), company_id("Hynix")
    idx.bulk_load(
        entities=[_company(nvda), _company(tsmc), _company(hynix)],
        relations=[_supplies(tsmc, nvda), _supplies(hynix, nvda)],
    )

    paths = idx.walk_paths(tsmc, nvda)
    assert [tsmc, nvda] in paths


def test_walk_paths_filtered_by_edge_type() -> None:
    idx = IndexLayer()
    nvda, amd = company_id("NVDA"), company_id("AMD")
    idx.bulk_load(
        entities=[_company(nvda), _company(amd)],
        relations=[
            _supplies(nvda, amd),
            _competes(nvda, amd),
        ],
    )
    # Only supplies_to edges allowed → one path.
    paths = idx.walk_paths(nvda, amd, edge_types=["supplies_to"])
    assert paths == [[nvda, amd]]
    # No edges allowed (nonexistent type) → no paths.
    assert idx.walk_paths(nvda, amd, edge_types=["regulated_by"]) == []


def test_neighbors_directional() -> None:
    idx = IndexLayer()
    nvda, tsmc, msft = company_id("NVDA"), company_id("TSMC"), company_id("Microsoft")
    idx.bulk_load(
        entities=[_company(nvda), _company(tsmc), _company(msft)],
        relations=[_supplies(tsmc, nvda), _supplies(nvda, msft)],
    )
    assert idx.neighbors(nvda, direction="out") == [msft]
    assert idx.neighbors(nvda, direction="in") == [tsmc]
    assert idx.neighbors(nvda, direction="both") == sorted([tsmc, msft])


def test_remove_entity_drops_indices_and_graph_node() -> None:
    idx = IndexLayer()
    idx.add_entity(_company("co:NVDA", ticker="NVDA"))
    idx.add_entity(_company("co:TSMC", ticker="TSMC"))
    rel = _supplies("co:TSMC", "co:NVDA")
    idx.add_relation(rel)
    idx.remove_entity("co:NVDA")

    assert idx.get_entity("co:NVDA") is None
    assert idx.find_by_ticker("NVDA") is None
    assert "co:NVDA" not in idx.graph
    # Incident relation removed by graph cascade but still in relations_by_id
    # until explicit remove_relation — that's expected; relations are first-class.
    assert rel.id in idx.relations_by_id


def test_remove_relation() -> None:
    idx = IndexLayer()
    nvda, tsmc = company_id("NVDA"), company_id("TSMC")
    rel = _supplies(tsmc, nvda)
    idx.bulk_load(entities=[_company(nvda), _company(tsmc)], relations=[rel])
    idx.remove_relation(rel.id)

    assert rel.id not in idx.relations_by_id
    assert rel.id not in idx.relations_by_source[tsmc]
    assert rel.id not in idx.relations_by_target[nvda]
    assert not idx.graph.has_edge(tsmc, nvda, key=rel.id)


def test_bulk_load_and_stats() -> None:
    idx = IndexLayer()
    idx.bulk_load(
        entities=[_company(company_id(t)) for t in ("NVDA", "TSMC", "AMD")],
        relations=[
            _supplies(company_id("TSMC"), company_id("NVDA")),
            _supplies(company_id("TSMC"), company_id("AMD")),
        ],
    )
    s = idx.stats()
    assert s["entities"] == 3
    assert s["relations"] == 2
    assert s["graph_nodes"] == 3
    assert s["graph_edges"] == 2


def test_accepts_dict_records_too() -> None:
    """add_entity/relation accept raw dicts (so we don't always need Pydantic)."""
    idx = IndexLayer()
    idx.add_entity({"id": "co:X", "kind": "Company", "labels": ["X"]})
    idx.add_relation(
        {
            "id": "r:test",
            "type": "supplies_to",
            "source_id": "co:X",
            "target_id": "co:Y",
        }
    )
    assert idx.get_entity("co:X") is not None
    assert idx.relations_by_id["r:test"]["source_id"] == "co:X"


@pytest.mark.parametrize("axis,value", [("sectors", "Semiconductor"), ("regions", "US")])
def test_facet_index_multi_axis(axis: str, value: str) -> None:
    idx = IndexLayer()
    idx.add_entity(_company("co:NVDA", sectors=["Semiconductor"], regions=["US"]))
    idx.add_entity(_company("co:TSMC", sectors=["Semiconductor"], regions=["TW"]))
    matches = {e["id"] for e in idx.list_by_facet(axis, value)}
    if axis == "sectors":
        assert matches == {"co:NVDA", "co:TSMC"}
    else:
        assert matches == {"co:NVDA"}
