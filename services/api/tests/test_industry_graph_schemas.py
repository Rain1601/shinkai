"""Schema-level tests for industry_graph: round-trip, validation, extras."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shinkai_api.industry_graph.schemas import (
    ChangeEntry,
    ChangesetSummary,
    EntityBase,
    FacetSet,
    ProvenanceRef,
    RelationBase,
    SnapshotMeta,
    WeightCell,
    company_id,
    relation_id,
    slugify,
    source_id,
    subtheme_id,
    theme_id,
    thesis_id,
)

_NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)


def _provenance() -> ProvenanceRef:
    return ProvenanceRef(
        source_id="src:ms_20260508",
        page=13,
        quote="TSMC AI semis revenue CAGR projected at 60% from 2024 to 2029e",
        confidence=0.95,
        evidence_type="hard_data",
        asserted_at=_NOW,
        asserted_by="run_test",
    )


# ============================================================
# Provenance
# ============================================================
def test_provenance_round_trip():
    p = _provenance()
    again = ProvenanceRef.model_validate(p.model_dump())
    assert again == p


def test_provenance_confidence_bounds():
    with pytest.raises(ValidationError):
        ProvenanceRef(
            source_id="src:x",
            confidence=1.5,
            asserted_at=_NOW,
        )


def test_provenance_extras_pass_through():
    p = ProvenanceRef.model_validate(
        {
            "source_id": "src:x",
            "asserted_at": _NOW.isoformat(),
            "future_field": "ok",  # extras allowed
        }
    )
    assert p.model_dump()["future_field"] == "ok"


# ============================================================
# FacetSet
# ============================================================
def test_facetset_defaults_empty():
    f = FacetSet()
    assert f.concept_level is None
    assert f.sectors == []
    assert f.regions == []


def test_facetset_extras_accepted():
    f = FacetSet.model_validate(
        {
            "sectors": ["Semiconductor"],
            "esg_score": 7.5,  # new axis, not declared
            "funding_stage": "public",
        }
    )
    dumped = f.model_dump()
    assert dumped["esg_score"] == 7.5
    assert dumped["funding_stage"] == "public"


# ============================================================
# EntityBase
# ============================================================
def _entity() -> EntityBase:
    return EntityBase(
        id="co:NVDA",
        kind="Company",
        labels=["NVIDIA Corporation", "英伟达"],
        aliases=["NVDA"],
        description="GPU & AI accelerator designer.",
        facets=FacetSet(sectors=["Semiconductor"], regions=["US"], chain_layers=["designer"]),
        attributes={"ticker": "NVDA", "market_cap_usd_bn": 3500},
        provenance=[_provenance()],
        confidence=1.0,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_entity_round_trip():
    e = _entity()
    again = EntityBase.model_validate(e.model_dump())
    assert again == e


def test_entity_kind_rejects_unknown():
    with pytest.raises(ValidationError):
        EntityBase(
            id="x:y",
            kind="UnknownKind",  # not in Literal
            created_at=_NOW,
            updated_at=_NOW,
        )


def test_entity_extras_in_attributes_open():
    # attributes is dict[str, Any] — accepts any payload, no schema migration
    e = EntityBase(
        id="bn:cowos_2026",
        kind="Bottleneck",
        attributes={
            "type": "capacity",
            "severity": "high",
            "status": "active",
            "weird_new_field": [1, 2, 3],  # open-ended
        },
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert e.attributes["weird_new_field"] == [1, 2, 3]


# ============================================================
# RelationBase + WeightCell
# ============================================================
def test_weight_cell_round_trip():
    w = WeightCell(
        period="2026",
        values={"buyer_spend": 0.78, "seller_revenue": 0.21, "lock_in": 0.95},
    )
    again = WeightCell.model_validate(w.model_dump())
    assert again == w


def test_relation_round_trip():
    r = RelationBase(
        id=relation_id("supplies_to", "co:TSMC", "co:NVDA", "2026"),
        type="supplies_to",
        source_id="co:TSMC",
        target_id="co:NVDA",
        weights=[
            WeightCell(period="2026", values={"buyer_spend": 0.78}),
            WeightCell(period="2027e", values={"buyer_spend": 0.75}),
        ],
        attributes={"is_bottleneck": True},
        provenance=[_provenance()],
        created_at=_NOW,
        updated_at=_NOW,
    )
    again = RelationBase.model_validate(r.model_dump())
    assert again == r
    assert r.id == "r:supplies_to~co_TSMC~co_NVDA~2026"


def test_relation_rejects_unknown_type():
    with pytest.raises(ValidationError):
        RelationBase(
            id="r:bad",
            type="not_a_real_type",  # not in Literal
            source_id="a",
            target_id="b",
            created_at=_NOW,
            updated_at=_NOW,
        )


# ============================================================
# Snapshot meta + change entry
# ============================================================
def test_snapshot_meta_round_trip():
    m = SnapshotMeta(
        version=42,
        parent_version=41,
        created_at=_NOW,
        created_by_run_id="run_abc",
        rationale="Ingested MS 20260508",
        changeset_summary=ChangesetSummary(
            entities_added=17,
            relations_added=42,
            bottlenecks_added=8,
        ),
    )
    again = SnapshotMeta.model_validate(m.model_dump())
    assert again == m


def test_change_entry_round_trip():
    c = ChangeEntry(
        op="insert",
        kind="entity",
        id="co:NVDA",
        after={"kind": "Company"},
        source_ref_id="src:ms_20260508",
        actor="run_abc",
        ts=_NOW,
    )
    again = ChangeEntry.model_validate(c.model_dump())
    assert again == c


# ============================================================
# ID helpers
# ============================================================
def test_slugify_basic():
    assert slugify("AI Infrastructure") == "ai_infrastructure"
    assert slugify("  Hello — World!! ") == "hello_world"
    assert slugify("CoWoS-L (silicon)") == "cowos_l_silicon"


def test_company_id_keeps_ticker_case():
    assert company_id("NVDA") == "co:NVDA"
    assert company_id("绿的谐波") == "co:绿的谐波"


def test_theme_vs_thesis_no_collision():
    # th:* is theme; ith:* is investment thesis — no overlap
    assert theme_id("AI").startswith("th:")
    assert thesis_id("MS NVDA 2026-05-08").startswith("ith:")


def test_subtheme_and_source_id():
    assert subtheme_id("AI Infrastructure") == "st:ai_infrastructure"
    assert source_id("MS 20260508 AI Infra") == "src:ms_20260508_ai_infra"


def test_relation_id_deterministic():
    a = relation_id("supplies_to", "co:TSMC", "co:NVDA", "2026")
    b = relation_id("supplies_to", "co:TSMC", "co:NVDA", "2026")
    assert a == b
    assert ":" in a and "~" in a


def test_relation_id_without_period():
    rid = relation_id("competes_with", "co:NVDA", "co:AMD")
    assert rid == "r:competes_with~co_NVDA~co_AMD"
