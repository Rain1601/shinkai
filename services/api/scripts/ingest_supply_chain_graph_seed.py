"""Seed the industry graph from a pre-harvested supply_chain_graph.json.

Reads ``/Users/rain/ResearchGraph/data/sop_v1/supply_chain_graph.json``
(11 targets × ~250 suppliers harvested by the earlier LLM pipeline) and
populates the industry graph via the function-tool surface.

This is the deterministic seed used by tests and by the demo. The agent-driven
DeepSeek ingestion (Stage 7) does the same thing using live LLM tool calls.

Usage::

    cd services/api
    SHINKAI_INDUSTRY_GRAPH_PATH=/tmp/ig.test \\
        uv run python scripts/ingest_supply_chain_graph_seed.py \\
        /Users/rain/ResearchGraph/data/sop_v1/supply_chain_graph.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow ``uv run python scripts/...`` from services/api.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shinkai_api.industry_graph import IndustryGraphStore
from shinkai_api.industry_graph.schemas import (
    bottleneck_id,
    company_id,
    key_data_id,
    relation_id,
    slugify,
    source_id,
    subtheme_id,
    thesis_id,
)


THEME_TARGETS = {"HBM", "OPTICAL", "POWER", "ROBOTICS"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _source_ref(sid: str, page: int | None = None, quote: str | None = None) -> dict:
    return {
        "source_id": sid,
        "page": page,
        "quote": quote,
        "confidence": 0.9,
        "evidence_type": "hard_data",
        "asserted_at": _now(),
    }


def _norm_publisher(text: str) -> str:
    """Extract a publisher token from short ``source_report`` strings."""
    m = re.match(r"\s*([A-Za-z]+)", text)
    return m.group(1).upper() if m else "UNKNOWN"


def _normalize_id(name: str, *, ticker: str | None = None) -> str:
    if ticker:
        ticker = ticker.strip().upper()
        if ticker and ticker != "PRIVATE" and ticker != "N/A":
            return company_id(ticker)
    return company_id(slugify(name))


async def _ingest_target(
    store: IndustryGraphStore,
    target_key: str,
    target_data: dict[str, Any],
) -> dict[str, int]:
    """Ingest one target's worth of data. Returns counts of objects created."""
    is_theme = target_key in THEME_TARGETS
    target_kind = "SubTheme" if is_theme else "Company"
    target_id_str = (
        subtheme_id(target_key) if is_theme else _normalize_id(target_key, ticker=target_key)
    )
    counts = {"entities": 0, "relations": 0, "bottlenecks": 0, "key_data": 0, "theses": 0}

    # ---------- sources first ----------
    source_index: dict[str, str] = {}  # human-readable label → source_id
    for src in target_data.get("sources", []):
        # Each source block has publisher, date, file, etc.
        publisher = src.get("publisher") or _norm_publisher(src.get("file", ""))
        title = src.get("title") or Path(src.get("file", "untitled")).name
        date = src.get("date") or "1970-01-01"
        sid = source_id(f"{publisher} {date} {title}")
        await store.upsert_entity(
            {
                "id": sid,
                "kind": "Source",
                "labels": [title],
                "description": f"{publisher} · {date}",
                "attributes": {
                    "publisher": publisher,
                    "title": title,
                    "date": date,
                    "url": src.get("url"),
                    "file": src.get("file"),
                    "tickers": [target_key] if not is_theme else [],
                },
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=None,
        )
        source_index[f"{publisher} {date.split('-')[1] if '-' in date else ''}"] = sid
        # Also key by file basename for matches by supplier.source_report
        source_index.setdefault(publisher, sid)
        counts["entities"] += 1

    # Fallback source for unattributed claims.
    fallback_sid = source_id(f"seed_{target_key}")
    await store.upsert_entity(
        {
            "id": fallback_sid,
            "kind": "Source",
            "labels": [f"Seed import for {target_key}"],
            "description": "Synthesized source for seed ingestion when no explicit source_report.",
            "attributes": {"publisher": "SEED", "date": "2026-06-21"},
            "created_at": _now(),
            "updated_at": _now(),
        },
        source_ref_id=None,
    )

    def _resolve_source(text: str | None) -> str:
        if not text:
            return fallback_sid
        # Try by publisher prefix ("MS 5/8" → "MS")
        pub = _norm_publisher(text)
        return source_index.get(pub, fallback_sid)

    # ---------- target entity ----------
    target_attrs: dict[str, Any] = {}
    if not is_theme:
        target_attrs["ticker"] = target_key
    await store.upsert_entity(
        {
            "id": target_id_str,
            "kind": target_kind,
            "labels": [target_key],
            "description": target_data.get("target_description"),
            "attributes": target_attrs,
            "created_at": _now(),
            "updated_at": _now(),
        },
        source_ref_id=fallback_sid,
    )
    counts["entities"] += 1

    # ---------- upstream supply chain ----------
    for layer in target_data.get("upstream_supply_chain", []):
        layer_name = layer.get("layer") or "unknown_layer"
        for supplier in layer.get("suppliers", []):
            sup_name = supplier.get("name")
            sup_ticker = supplier.get("ticker")
            if not sup_name:
                continue
            sup_id = _normalize_id(sup_name, ticker=sup_ticker)
            sup_source = _resolve_source(supplier.get("source_report"))
            await store.upsert_entity(
                {
                    "id": sup_id,
                    "kind": "Company",
                    "labels": [sup_name],
                    "aliases": [sup_ticker] if sup_ticker else [],
                    "description": supplier.get("role"),
                    "facets": {
                        "regions": [supplier.get("country")] if supplier.get("country") else [],
                        "chain_layers": [layer_name],
                    },
                    "attributes": {
                        "ticker": sup_ticker if sup_ticker else None,
                        "role": supplier.get("role"),
                        "notes": supplier.get("notes"),
                    },
                    "created_at": _now(),
                    "updated_at": _now(),
                },
                source_ref_id=sup_source,
            )
            counts["entities"] += 1

            # supplies_to relation: supplier → target
            await store.upsert_relation(
                {
                    "id": relation_id("supplies_to", sup_id, target_id_str, "2026e"),
                    "type": "supplies_to",
                    "source_id": sup_id,
                    "target_id": target_id_str,
                    "weights": [
                        {
                            "period": "2026e",
                            "values": {},
                        }
                    ],
                    "attributes": {
                        "share_or_capacity": supplier.get("share_or_capacity"),
                        "layer": layer_name,
                        "is_bottleneck": layer.get("is_bottleneck", False),
                        "criticality": layer.get("criticality"),
                    },
                    "provenance": [_source_ref(sup_source)],
                    "created_at": _now(),
                    "updated_at": _now(),
                },
                source_ref_id=sup_source,
            )
            counts["relations"] += 1

    # ---------- downstream customers ----------
    for cust in target_data.get("downstream_customers", []):
        cust_name = cust.get("customer")
        if not cust_name:
            continue
        cid = _normalize_id(cust_name)
        cust_source = _resolve_source(cust.get("source_report"))
        await store.upsert_entity(
            {
                "id": cid,
                "kind": "Company",
                "labels": [cust_name],
                "description": cust.get("use_case"),
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=cust_source,
        )
        counts["entities"] += 1
        # supplies_to: target → customer
        await store.upsert_relation(
            {
                "id": relation_id("supplies_to", target_id_str, cid, "2026e"),
                "type": "supplies_to",
                "source_id": target_id_str,
                "target_id": cid,
                "weights": [{"period": "2026e", "values": {}}],
                "attributes": {
                    "use_case": cust.get("use_case"),
                    "share_or_capacity": cust.get("share"),
                },
                "provenance": [_source_ref(cust_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=cust_source,
        )
        counts["relations"] += 1

    # ---------- competitors ----------
    for comp in target_data.get("competitors", []):
        comp_name = comp.get("name")
        if not comp_name:
            continue
        cid = _normalize_id(comp_name, ticker=comp.get("ticker"))
        comp_source = _resolve_source(comp.get("source_report"))
        await store.upsert_entity(
            {
                "id": cid,
                "kind": "Company",
                "labels": [comp_name],
                "aliases": [comp["ticker"]] if comp.get("ticker") else [],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=comp_source,
        )
        counts["entities"] += 1
        await store.upsert_relation(
            {
                "id": relation_id("competes_with", target_id_str, cid),
                "type": "competes_with",
                "source_id": target_id_str,
                "target_id": cid,
                "weights": [],
                "attributes": {
                    "relationship": comp.get("relationship"),
                    "threat_level": comp.get("threat_level"),
                    "specific_threat": comp.get("specific_threat"),
                },
                "provenance": [_source_ref(comp_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=comp_source,
        )
        counts["relations"] += 1

    # ---------- bottlenecks ----------
    for i, bn in enumerate(target_data.get("bottlenecks_and_risks", [])):
        slug = f"{target_key}_{bn.get('type', 'risk')}_{i}"
        bid = bottleneck_id(slug)
        bn_source = _resolve_source(bn.get("source_report"))
        await store.upsert_entity(
            {
                "id": bid,
                "kind": "Bottleneck",
                "labels": [slug],
                "description": bn.get("description"),
                "attributes": {
                    "type": bn.get("type"),
                    "severity": bn.get("severity"),
                    "status": "active",
                    "affects": [target_id_str],
                },
                "provenance": [_source_ref(bn_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=bn_source,
        )
        # affects relation
        await store.upsert_relation(
            {
                "id": relation_id("affects", bid, target_id_str),
                "type": "affects",
                "source_id": bid,
                "target_id": target_id_str,
                "weights": [],
                "attributes": {},
                "provenance": [_source_ref(bn_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=bn_source,
        )
        counts["bottlenecks"] += 1
        counts["entities"] += 1
        counts["relations"] += 1

    # ---------- key data points ----------
    for kdp in target_data.get("key_data_points", []):
        metric = kdp.get("metric")
        period = kdp.get("period") or "unknown"
        if not metric:
            continue
        slug = f"{target_key}_{metric}_{period}"
        kdp_id = key_data_id(slug)
        kdp_source = _resolve_source(kdp.get("source_report"))
        await store.upsert_entity(
            {
                "id": kdp_id,
                "kind": "KeyDataPoint",
                "labels": [metric],
                "description": f"{metric} = {kdp.get('value')} ({period})",
                "attributes": {
                    "subject_id": target_id_str,
                    "metric": metric,
                    "value": kdp.get("value"),
                    "period": period,
                },
                "provenance": [_source_ref(kdp_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=kdp_source,
        )
        await store.upsert_relation(
            {
                "id": relation_id("key_data_about", kdp_id, target_id_str),
                "type": "key_data_about",
                "source_id": kdp_id,
                "target_id": target_id_str,
                "weights": [],
                "attributes": {},
                "provenance": [_source_ref(kdp_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=kdp_source,
        )
        counts["key_data"] += 1
        counts["entities"] += 1
        counts["relations"] += 1

    # ---------- investment implications ----------
    implications = target_data.get("investment_implications") or {}
    stocks_to_watch = implications.get("stocks_to_watch") or []
    if stocks_to_watch:
        slug = f"{target_key}_investment_thesis"
        thid = thesis_id(slug)
        thesis_source = _resolve_source(
            (stocks_to_watch[0].get("source_report") if stocks_to_watch else None)
        )
        await store.upsert_entity(
            {
                "id": thid,
                "kind": "InvestmentThesis",
                "labels": [slug],
                "description": implications.get("summary") or "Stocks to watch",
                "attributes": {
                    "target_id": target_id_str,
                    "stocks_to_watch": stocks_to_watch,
                    "bias": "constructive",
                    "horizon": "medium",
                },
                "provenance": [_source_ref(thesis_source)],
                "created_at": _now(),
                "updated_at": _now(),
            },
            source_ref_id=thesis_source,
        )
        # watched_in relation per stock (when ticker present)
        for s in stocks_to_watch:
            name = s.get("name") or s.get("ticker") or ""
            ticker_match = re.search(r"\(([^)]+)\)", name)
            ticker = ticker_match.group(1) if ticker_match else None
            cid = _normalize_id(name, ticker=ticker)
            await store.upsert_relation(
                {
                    "id": relation_id("watched_in", thid, cid),
                    "type": "watched_in",
                    "source_id": thid,
                    "target_id": cid,
                    "weights": [],
                    "attributes": {"rationale": s.get("rationale"), "pt": s.get("pt")},
                    "provenance": [_source_ref(thesis_source)],
                    "created_at": _now(),
                    "updated_at": _now(),
                },
                source_ref_id=thesis_source,
            )
        counts["theses"] += 1
        counts["entities"] += 1

    return counts


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="supply_chain_graph.json path")
    p.add_argument("--rationale", default="Initial seed from supply_chain_graph.json")
    args = p.parse_args()

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}")
        return 1

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    targets = raw.get("targets") or {}

    store = IndustryGraphStore()
    await store.load()

    print(f"Ingesting {len(targets)} targets…")
    totals = {"entities": 0, "relations": 0, "bottlenecks": 0, "key_data": 0, "theses": 0}
    for tkey, tdata in targets.items():
        counts = await _ingest_target(store, tkey, tdata)
        for k, v in counts.items():
            totals[k] += v
        print(
            f"  {tkey:>10}: +{counts['entities']:>3} entities  "
            f"+{counts['relations']:>3} relations  "
            f"+{counts['bottlenecks']} bottlenecks  "
            f"+{counts['key_data']} KDP  "
            f"+{counts['theses']} theses"
        )

    meta = await store.commit_snapshot(rationale=args.rationale)
    stats = store.stats()
    print(f"\nSnapshot v{meta.version} committed.")
    print(f"Totals: {totals}")
    print(f"Store stats: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
