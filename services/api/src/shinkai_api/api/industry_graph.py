"""Read-only export endpoint for the industry knowledge graph.

The demo at ``apps/web/public/industry-graph-live.html`` fetches this to draw
real ingested data (post-seed or post-agent-session) instead of the inline
mock used by ``industry-graph-demo.html``.

Translation rules (store → demo shape):
- Entity.kind passes through (Company, SubTheme, Product, Component, Bottleneck,
  KeyDataPoint, InvestmentThesis, Source, etc).
- ``layer`` is derived from facets.supply_layer[0] when present, else falls
  back to a kind-derived default. Demo strata are: designer, foundry,
  advanced_packaging, memory, testing, assembly, networking, optical,
  power, theme.
- ``desc`` = entity.description or first attributes.summary.
- ``confidence`` taken from any provenance entry's ``confidence`` (max).
- ``source`` = display label of the first provenance source (publisher + page).
- ``aliases`` passes through.

Relations: id, source/target, type, weights → ``wbp`` keyed by period, plus
``confidence`` and ``evidence_type`` lifted from the first provenance entry.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from shinkai_api.industry_graph import IndustryGraphStore

router = APIRouter(prefix="/industry_graph", tags=["industry_graph"])

_store: IndustryGraphStore | None = None
_load_lock = asyncio.Lock()


async def _get_store() -> IndustryGraphStore:
    global _store
    if _store is not None:
        return _store
    async with _load_lock:
        if _store is None:
            store = IndustryGraphStore()
            await store.load()
            _store = store
    return _store


def _layer_from_facets(facets: dict[str, Any] | None, kind: str) -> str | None:
    """Pick a canonical strata for the entity.

    Order of precedence:
    1. ``facets.supply_layer`` (if explicit — wins).
    2. Keyword match against ``facets.chain_layers`` (seed data uses this
       Chinese-named facet; ~90 raw values are bucketed below).
    3. Kind-derived default.
    """
    if isinstance(facets, dict):
        sl = facets.get("supply_layer")
        if isinstance(sl, list) and sl:
            return str(sl[0])
        if isinstance(sl, str):
            return sl
        cl = facets.get("chain_layers")
        cl_list = cl if isinstance(cl, list) else ([cl] if isinstance(cl, str) else [])
        for raw in cl_list:
            mapped = _map_chain_layer(str(raw))
            if mapped:
                return mapped
    return _DEFAULT_LAYER_BY_KIND.get(kind)


# Canonical strata — order matches the typical supply-chain depth from the
# anchor (top of list = closest to end buyer, bottom = deepest upstream).
LAYER_ORDER = [
    "buyer",
    "ai_model",
    "designer",
    "assembly",
    "advanced_packaging",
    "memory",
    "testing",
    "foundry",
    "optical",
    "robotics",
    "battery",
    "power",
    "cooling",
    "infrastructure",
    "passive",
    "materials",
    "theme",
]

# Keyword rules — match in order; first hit wins. Substrings, case-insensitive.
# Keep specific rules above more generic ones (CoWoS before "封装"; HBM before "memory").
_LAYER_RULES: list[tuple[str, list[str]]] = [
    ("foundry", ["晶圆代工", "logic foundry", "advanced foundry", "硅光子芯片代工", "前道设备"]),
    ("advanced_packaging", [
        "先进封装", "cowos", "soic", "aip", "sip 封装", "光学封装", "cpo/光学",
        "ic基板", "ic substrate", "pcb", "后道设备",
    ]),
    ("memory", ["hbm", "内存", "dram", "nand"]),
    ("testing", ["芯片测试", "chip testing", "osat"]),
    ("optical", [
        "光学收发", "光收发", "光纤阵列", "fau coupling", "光通信", "激光光源",
        "laser source", "optical transceiver", "铜互连", "aec", "active electrical",
        "networking infrastructure", "数据中心网络",
    ]),
    ("assembly", [
        "ems", "odm", "整机组装", "服务器组装", "pc oem", "ar/vr",
        "oled", "摄像头", "ois", "vcm", "haptic", "hinge", "铰链",
        "casing", "casing & frame", "结构件", "gigacasting",
        "ic substrates (abf)",
    ]),
    ("robotics", [
        "人形机器人", "dexterous hand", "灵巧手", "motors & actuator", "电机",
        "actuator", "reducer", "减速器", "screws", "精密丝杠", "bearing", "轴承",
        "sensors (lidar", "传感器 / sensors", "外部 actuator", "harmonic reducer",
    ]),
    ("battery", [
        "battery cell", "battery pack", "电池芯", "电池 (battery",
        "电池 / batteries", "megapack", "bess", "energy storage",
        "锂原材料", "battery energy storage",
    ]),
    ("power", [
        "power distribution", "ups", "nuclear", "gas turbine",
        "transformer", "grid equipment", "dc backup", "dc power",
        "数据中心电源", "datacenter power", "power semiconductor",
        "化合物半导体", "电源管理",
    ]),
    ("cooling", ["cooling", "冷却"]),
    ("materials", ["raw material", "rare earth", "稀土", "critical mineral"]),
    ("infrastructure", [
        "数据中心基础设施", "dc infrastructure", "external hyperscale",
        "云算力", "物流", "data center construction", "colocation",
    ]),
    ("passive", ["mlcc", "被动元件"]),
    ("ai_model", [
        "ai模型", "ai 模型", "ai 脑模型", "ai foundation model",
        "strategic ai model", "physical ai foundation",
    ]),
    ("designer", [
        "asic", "soc", "gpu", "tpu", "芯片设计", "ai加速", "ai 加速",
        "compute silicon", "半导体计算", "modem", "bmc", "图像传感器",
        "image sensor", "driver ic", "驱动 ic", "ai 训练算力",
        "design services", "应用处理器", "application processor",
        "5g 调制",
    ]),
]


def _map_chain_layer(value: str) -> str | None:
    lower = value.lower()
    for layer, keywords in _LAYER_RULES:
        for kw in keywords:
            if kw in lower:
                return layer
    return None


_DEFAULT_LAYER_BY_KIND = {
    "SubTheme": "theme",
    "Product": "designer",
    "Component": "designer",
    "Bottleneck": None,
    "InvestmentThesis": None,
    "KeyDataPoint": None,
    "Source": None,
}


def _source_label(prov: dict[str, Any], src_lookup: dict[str, dict[str, Any]]) -> str:
    sid = prov.get("source_id")
    if not sid:
        return ""
    src = src_lookup.get(sid)
    if not src:
        return sid
    attrs = src.get("attributes") or {}
    pub = attrs.get("publisher") or ""
    title = attrs.get("title") or ""
    page = prov.get("page")
    parts = [p for p in [pub, title] if p]
    base = " · ".join(parts) if parts else sid
    return f"{base} p.{page}" if page else base


def _project_entity(
    e: dict[str, Any], src_lookup: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    kind = e.get("kind") or "Entity"
    labels = e.get("labels") or []
    label = labels[0] if labels else (e.get("id") or "?")
    layer = _layer_from_facets(e.get("facets"), kind)
    attrs = e.get("attributes") or {}
    prov = e.get("provenance") or []
    first = prov[0] if prov else {}
    confs = [p.get("confidence") for p in prov if isinstance(p.get("confidence"), int | float)]
    confidence = max(confs) if confs else None
    return {
        "id": e["id"],
        "label": label,
        "kind": kind,
        "layer": layer,
        "desc": e.get("description") or attrs.get("summary") or "",
        "aliases": e.get("aliases") or [],
        "confidence": confidence,
        "source": _source_label(first, src_lookup),
        "facets": e.get("facets") or {},
        "attributes": attrs,
    }


def _project_relation(
    r: dict[str, Any], src_lookup: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    weights = r.get("weights") or []
    wbp: dict[int, list[float]] = {}
    for w in weights:
        period = w.get("period")
        if not isinstance(period, int):
            try:
                period = int(period)
            except (TypeError, ValueError):
                continue
        share = w.get("share")
        delta = w.get("delta")
        conf = w.get("confidence")
        # Demo format: [share, delta, confidence]; gracefully accept missing.
        row = [
            float(share) if isinstance(share, int | float) else 0.0,
            float(delta) if isinstance(delta, int | float) else 0.0,
            float(conf) if isinstance(conf, int | float) else 0.0,
        ]
        wbp[period] = row
    prov = r.get("provenance") or []
    first = prov[0] if prov else {}
    return {
        "id": r["id"],
        "source": r["source_id"],
        "target": r["target_id"],
        "type": r["type"],
        "wbp": wbp,
        "confidence": first.get("confidence"),
        "evidence_type": first.get("evidence_type"),
        "evidence_ref": _source_label(first, src_lookup),
    }


@router.get("/stats")
async def stats() -> dict[str, Any]:
    store = await _get_store()
    s = store.index.stats()
    return {
        "entities": s.get("entities", 0),
        "relations": s.get("relations", 0),
        "kinds": s.get("kinds", 0),
        "facets": s.get("facets", 0),
        "tickers": s.get("tickers", 0),
        "snapshot_version": await store.snapshots.latest_version(),
    }


@router.get("/export")
async def export(
    kind: str | None = None,
    layer: str | None = None,
    limit: int | None = None,
    anchor: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    """Return the store as ``{nodes: [...], edges: [...]}`` for the live demo.

    Two modes:
    - **Anchor mode** (``anchor`` set): returns the entity plus its ``depth``-hop
      neighborhood via undirected BFS over non-deprecated relations. Other
      filters are ignored. This is the demo's anchor-focused view.
    - **Catalog mode** (default): returns entities optionally filtered by kind
      and layer, capped by ``limit``. Edges restricted to the visible nodes.
    """
    store = await _get_store()
    src_lookup = {
        e["id"]: e
        for e in store.index.by_id.values()
        if (e.get("kind") == "Source")
    }
    by_id = store.index.by_id

    if anchor:
        if anchor not in by_id:
            return {
                "nodes": [],
                "edges": [],
                "meta": {
                    "node_count": 0,
                    "edge_count": 0,
                    "anchor": anchor,
                    "error": "anchor_not_found",
                },
            }
        # BFS up to `depth` hops over non-deprecated relations.
        keep: set[str] = {anchor}
        frontier = {anchor}
        for _ in range(max(0, depth)):
            next_frontier: set[str] = set()
            for r in store.index.relations_by_id.values():
                if r.get("deprecated_at"):
                    continue
                a, b = r["source_id"], r["target_id"]
                if a in frontier and b not in keep:
                    next_frontier.add(b)
                if b in frontier and a not in keep:
                    next_frontier.add(a)
            if not next_frontier:
                break
            keep.update(next_frontier)
            frontier = next_frontier

        nodes_raw = [by_id[i] for i in keep if i in by_id and not by_id[i].get("deprecated_at")]
        nodes = [_project_entity(e, src_lookup) for e in nodes_raw]
        node_ids = set(keep)
        edges = []
        for r in store.index.relations_by_id.values():
            if r.get("deprecated_at"):
                continue
            if r["source_id"] in node_ids and r["target_id"] in node_ids:
                edges.append(_project_relation(r, src_lookup))
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "anchor": anchor,
                "depth": depth,
                "snapshot_version": await store.snapshots.latest_version(),
            },
        }

    # Catalog mode.
    nodes: list[dict[str, Any]] = []
    for e in by_id.values():
        if e.get("deprecated_at"):
            continue
        if kind and e.get("kind") != kind:
            continue
        projected = _project_entity(e, src_lookup)
        if layer and projected.get("layer") != layer:
            continue
        nodes.append(projected)
        if limit is not None and len(nodes) >= limit:
            break
    node_ids = {n["id"] for n in nodes}
    edges: list[dict[str, Any]] = []
    for r in store.index.relations_by_id.values():
        if r.get("deprecated_at"):
            continue
        if r["source_id"] not in node_ids or r["target_id"] not in node_ids:
            continue
        edges.append(_project_relation(r, src_lookup))
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "snapshot_version": await store.snapshots.latest_version(),
        },
    }


@router.get("/anchors")
async def anchors(limit: int = 80) -> dict[str, Any]:
    """Companies ranked by edge degree — feeds the anchor selector dropdown."""
    store = await _get_store()
    counts: dict[str, int] = {}
    for r in store.index.relations_by_id.values():
        if r.get("deprecated_at"):
            continue
        counts[r["source_id"]] = counts.get(r["source_id"], 0) + 1
        counts[r["target_id"]] = counts.get(r["target_id"], 0) + 1
    rows = []
    for eid, ent in store.index.by_id.items():
        if ent.get("kind") != "Company" or ent.get("deprecated_at"):
            continue
        labels = ent.get("labels") or []
        rows.append(
            {
                "id": eid,
                "label": labels[0] if labels else eid,
                "degree": counts.get(eid, 0),
                "ticker": (ent.get("attributes") or {}).get("ticker"),
            }
        )
    rows.sort(key=lambda r: (-r["degree"], r["label"]))
    return {"anchors": rows[:limit]}


@router.post("/_reload")
async def reload_store() -> dict[str, Any]:
    """Drop the cached singleton — next request rereads disk. Dev helper."""
    global _store
    _store = None
    s = await _get_store()
    return {"ok": True, "stats": s.index.stats()}
