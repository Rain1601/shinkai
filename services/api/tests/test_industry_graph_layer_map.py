"""Tests for canonical supply_layer derivation.

Covers both the pure mapper (``layer_map.derive_supply_layer``) and the
write-path integration via ``IndustryGraphStore.upsert_entity`` — every
agent-created Company should carry a canonical ``facets.supply_layer``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from shinkai_api.industry_graph import IndustryGraphStore
from shinkai_api.industry_graph.layer_map import (
    LAYER_ORDER,
    VALID_LAYERS,
    derive_supply_layer,
    map_chain_layer,
)


# ── pure mapper ──────────────────────────────────────────────────────────
def test_explicit_supply_layer_wins() -> None:
    assert derive_supply_layer({"supply_layer": "foundry"}) == "foundry"
    assert derive_supply_layer({"supply_layer": ["memory", "designer"]}) == "memory"


def test_chain_layer_keyword_inference() -> None:
    samples = [
        ("晶圆代工 (Foundry)", "foundry"),
        ("先进封装 / CoWoS", "advanced_packaging"),
        ("HBM 内存 (High-Bandwidth Memory)", "memory"),
        ("芯片测试 (Chip Testing — OSAT & Equipment)", "testing"),
        ("EMS / 整机组装", "assembly"),
        ("Datacenter Cooling", "cooling"),
        ("Power Semiconductors (SiC / GaN)", "power"),
        ("光通信 / CPO (Optical Networking — CPO and Transceivers)", "optical"),
        ("Rare Earth Materials", "materials"),
        ("AI 脑模型 / Physical AI Foundation Models", "ai_model"),
    ]
    for raw, expected in samples:
        assert map_chain_layer(raw) == expected, raw


def test_chain_layer_falls_back_to_kind_default() -> None:
    # No chain_layers, but SubTheme kind → theme.
    assert derive_supply_layer({}, "SubTheme") == "theme"
    # No facets, KeyDataPoint → None (not in default map).
    assert derive_supply_layer(None, "KeyDataPoint") is None


def test_unknown_chain_layer_returns_none() -> None:
    # Pick a phrase with no overlap with any rule keyword.
    assert map_chain_layer("Underwater geothermal vent prospecting") is None


def test_layer_order_is_canonical_set() -> None:
    assert set(LAYER_ORDER) == set(VALID_LAYERS)
    assert len(LAYER_ORDER) == len(VALID_LAYERS)  # no dupes


# ── write-path integration ───────────────────────────────────────────────
def _store(tmp_path: Path) -> IndustryGraphStore:
    s = IndustryGraphStore(root=tmp_path)
    asyncio.run(s.load())
    return s


def test_upsert_entity_auto_fills_supply_layer_from_chain_layers(tmp_path: Path) -> None:
    s = _store(tmp_path)

    async def run() -> None:
        # First register a source the entity can cite.
        src_ref = await s.upsert_entity(
            {
                "id": "src:test",
                "kind": "Source",
                "labels": ["test"],
                "attributes": {"publisher": "T", "title": "t", "date": "2026-06-21"},
            },
            source_ref_id=None,
        )
        assert src_ref["action"] == "created"

        # Upsert a Company with chain_layers but NO supply_layer.
        res = await s.upsert_entity(
            {
                "id": "co:TEST",
                "kind": "Company",
                "labels": ["TestCo"],
                "facets": {"chain_layers": ["先进封装 / CoWoS"]},
            },
            source_ref_id="src:test",
        )
        assert res["action"] == "created"
        stored = s.index.by_id["co:TEST"]
        assert stored["facets"]["supply_layer"] == "advanced_packaging"
        # The original chain_layers facet must be preserved.
        assert "先进封装 / CoWoS" in stored["facets"]["chain_layers"]

    asyncio.run(run())


def test_upsert_entity_preserves_explicit_supply_layer(tmp_path: Path) -> None:
    """If the agent already set supply_layer, don't second-guess it."""
    s = _store(tmp_path)

    async def run() -> None:
        await s.upsert_entity(
            {
                "id": "src:t",
                "kind": "Source",
                "labels": ["t"],
                "attributes": {"publisher": "T", "title": "t", "date": "2026-06-21"},
            },
            source_ref_id=None,
        )
        # Explicit supply_layer should win even if chain_layers would map elsewhere.
        await s.upsert_entity(
            {
                "id": "co:NUANCE",
                "kind": "Company",
                "labels": ["Nuance"],
                "facets": {
                    "supply_layer": "designer",
                    "chain_layers": ["HBM 生产商"],  # would map to memory
                },
            },
            source_ref_id="src:t",
        )
        assert s.index.by_id["co:NUANCE"]["facets"]["supply_layer"] == "designer"

    asyncio.run(run())


def test_upsert_entity_no_facets_uses_kind_default(tmp_path: Path) -> None:
    s = _store(tmp_path)

    async def run() -> None:
        await s.upsert_entity(
            {
                "id": "src:t",
                "kind": "Source",
                "labels": ["t"],
                "attributes": {"publisher": "T", "title": "t", "date": "2026-06-21"},
            },
            source_ref_id=None,
        )
        # SubTheme → theme
        await s.upsert_entity(
            {"id": "st:ai_infra", "kind": "SubTheme", "labels": ["AI Infrastructure"]},
            source_ref_id="src:t",
        )
        assert s.index.by_id["st:ai_infra"]["facets"]["supply_layer"] == "theme"

    asyncio.run(run())


def test_upsert_entity_update_does_not_clobber_supply_layer(tmp_path: Path) -> None:
    """An update that omits facets should not erase the previously-stored
    supply_layer."""
    s = _store(tmp_path)

    async def run() -> None:
        await s.upsert_entity(
            {
                "id": "src:t",
                "kind": "Source",
                "labels": ["t"],
                "attributes": {"publisher": "T", "title": "t", "date": "2026-06-21"},
            },
            source_ref_id=None,
        )
        await s.upsert_entity(
            {
                "id": "co:TSMC2",
                "kind": "Company",
                "labels": ["TSMC2"],
                "facets": {"chain_layers": ["晶圆代工"]},
            },
            source_ref_id="src:t",
        )
        assert s.index.by_id["co:TSMC2"]["facets"]["supply_layer"] == "foundry"

        # Update: add a description, no facets at all.
        await s.upsert_entity(
            {
                "id": "co:TSMC2",
                "kind": "Company",
                "labels": ["TSMC2"],
                "description": "Updated bio.",
            },
            source_ref_id="src:t",
        )
        # Original layer must survive the merge.
        assert s.index.by_id["co:TSMC2"]["facets"]["supply_layer"] == "foundry"
        assert s.index.by_id["co:TSMC2"]["description"] == "Updated bio."

    asyncio.run(run())
