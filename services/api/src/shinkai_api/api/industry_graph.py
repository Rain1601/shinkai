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
import os
from datetime import UTC
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from shinkai_api.industry_graph import (
    IndustryGraphStore,
    Subject,
    SubjectStore,
    SubjectVersion,
)
from shinkai_api.industry_graph.layer_map import derive_supply_layer
from shinkai_api.industry_graph.subjects import (
    SubjectLockBusy,
    finish_subject_run,
    prepare_subject_run,
)
from shinkai_api.llm.deepseek import DeepSeekClient
from shinkai_api.themes import default_theme_event_store
from shinkai_api.themes.events import ThemeEvent

router = APIRouter(prefix="/industry_graph", tags=["industry_graph"])

_store: IndustryGraphStore | None = None
_subject_store: SubjectStore | None = None
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


async def _get_subject_store() -> SubjectStore:
    global _subject_store
    if _subject_store is not None:
        return _subject_store
    graph = await _get_store()
    async with _load_lock:
        if _subject_store is None:
            ss = SubjectStore(fs=graph.fs)
            await ss.load()
            _subject_store = ss
    return _subject_store


def _build_deepseek_client() -> DeepSeekClient:
    """Construct a DeepSeek client from env settings. Raises 503 if no key.

    Falls back to the constructor default model (deepseek-chat); the harness
    side uses settings.llm_model — wire to it once the routes start sharing
    that config import.
    """
    key = os.environ.get("SHINKAI_DEEPSEEK_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SHINKAI_DEEPSEEK_API_KEY not configured",
        )
    model = os.environ.get("SHINKAI_LLM_MODEL") or "deepseek-chat"
    return DeepSeekClient(api_key=key, model=model)


def _layer_from_facets(facets: dict[str, Any] | None, kind: str) -> str | None:
    """Thin wrapper over the shared layer-map module."""
    return derive_supply_layer(facets, kind)


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


def _anchor_neighborhood(
    *,
    entities: dict[str, dict[str, Any]],
    relations: dict[str, dict[str, Any]],
    anchor: str,
    depth: int,
) -> dict[str, Any]:
    """Reusable BFS + projection over any state dict (current or reconstructed).

    Used by ``/export?anchor=…`` and ``/subjects/{id}/versions/{v}/graph``.
    """
    if anchor not in entities:
        return {
            "nodes": [],
            "edges": [],
            "meta": {
                "node_count": 0,
                "edge_count": 0,
                "anchor": anchor,
                "error": "anchor_not_in_state",
            },
        }
    src_lookup = {
        eid: e for eid, e in entities.items() if e.get("kind") == "Source"
    }
    keep: set[str] = {anchor}
    frontier = {anchor}
    for _ in range(max(0, depth)):
        next_frontier: set[str] = set()
        for r in relations.values():
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

    nodes_raw = [
        entities[i] for i in keep if i in entities and not entities[i].get("deprecated_at")
    ]
    nodes = [_project_entity(e, src_lookup) for e in nodes_raw]
    edges: list[dict[str, Any]] = []
    for r in relations.values():
        if r.get("deprecated_at"):
            continue
        if r["source_id"] in keep and r["target_id"] in keep:
            edges.append(_project_relation(r, src_lookup))
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "anchor": anchor,
            "depth": depth,
        },
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
        out = _anchor_neighborhood(
            entities=dict(by_id),
            relations=dict(store.index.relations_by_id),
            anchor=anchor,
            depth=depth,
        )
        if out["meta"].get("error") == "anchor_not_in_state":
            out["meta"]["error"] = "anchor_not_found"
        out["meta"]["snapshot_version"] = await store.snapshots.latest_version()
        return out

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
    """Drop the cached singletons — next request rereads disk. Dev helper."""
    global _store, _subject_store
    _store = None
    _subject_store = None
    s = await _get_store()
    return {"ok": True, "stats": s.index.stats()}


# ── Subjects ───────────────────────────────────────────────────────────────


class SubjectRunRequest(BaseModel):
    triggered_by: str = Field(default="manual", pattern="^(manual|schedule|agent)$")
    task_override: str | None = None
    max_turns: int = Field(default=20, ge=1, le=100)


def _subject_to_dict(s: Subject) -> dict[str, Any]:
    return s.model_dump(mode="json")


def _version_to_dict(v: SubjectVersion) -> dict[str, Any]:
    return v.model_dump(mode="json")


@router.get("/subjects")
async def list_subjects() -> dict[str, Any]:
    """All Subjects with their latest version meta — feeds the list page."""
    ss = await _get_subject_store()
    rows = await ss.list_subjects()
    out: list[dict[str, Any]] = []
    for subj in rows:
        versions = await ss.list_versions(subj.id)
        latest = versions[-1] if versions else None
        out.append(
            {
                **_subject_to_dict(subj),
                "version_count": len(versions),
                "latest_version": _version_to_dict(latest) if latest else None,
            }
        )
    # Sort by recency of last activity (most recent ended_at first); subjects
    # without versions go to the bottom.
    def _key(item: dict[str, Any]) -> tuple[int, str]:
        lv = item.get("latest_version") or {}
        return (0 if lv.get("ended_at") else 1, lv.get("ended_at") or item["id"])

    out.sort(key=_key)
    return {"subjects": out}


@router.get("/subjects/{subject_id}")
async def get_subject(subject_id: str) -> dict[str, Any]:
    ss = await _get_subject_store()
    subj = await ss.get_subject(subject_id)
    if subj is None:
        raise HTTPException(status_code=404, detail="subject not found")
    versions = await ss.list_versions(subject_id)
    return {
        **_subject_to_dict(subj),
        "versions": [_version_to_dict(v) for v in versions],
    }


async def _resolve_version(
    subject_id: str, version_no: int
) -> tuple[Subject, SubjectVersion]:
    ss = await _get_subject_store()
    subj = await ss.get_subject(subject_id)
    if subj is None:
        raise HTTPException(status_code=404, detail="subject not found")
    versions = await ss.list_versions(subject_id)
    target = next((v for v in versions if v.version_no == version_no), None)
    if target is None:
        raise HTTPException(status_code=404, detail="version not found")
    return subj, target


@router.get("/subjects/{subject_id}/versions/{version_no}")
async def get_subject_version(subject_id: str, version_no: int) -> dict[str, Any]:
    """Detail card for one version, including the change list rolled up to
    the scope frontier."""
    _, target = await _resolve_version(subject_id, version_no)
    graph = await _get_store()
    changes: list[dict[str, Any]] = []
    scope = set(target.scope_node_ids)
    if scope and target.snapshot_to > target.snapshot_from:
        for v in range(target.snapshot_from + 1, target.snapshot_to + 1):
            cs = await graph.snapshots.load_changes(v)
            for c in cs:
                if c.kind == "entity" and c.id in scope:
                    changes.append(c.model_dump(mode="json"))
                elif c.kind == "relation":
                    rec = c.after or c.before or {}
                    if (
                        c.id in scope
                        or rec.get("source_id") in scope
                        or rec.get("target_id") in scope
                    ):
                        changes.append(c.model_dump(mode="json"))
    return {**_version_to_dict(target), "changes": changes}


async def _events_for_subject(subject: Subject) -> list[ThemeEvent]:
    """Resolve the event feed for one Subject.

    - Theme subject: feed is ``ThemeEventStore.list_by_theme(<slug>)`` where
      the slug is the ``target_entity_id`` stripped of its ``st:`` prefix.
    - Company subject: scan all events and keep those whose ``tickers``
      list contains the Company's ticker (the part after ``co:``).
    """
    raw = subject.target_entity_id
    slug = raw.split(":", 1)[-1] if ":" in raw else raw
    if subject.type == "theme":
        return await default_theme_event_store.list_by_theme(slug)
    # Company: filter all events by ticker membership. We pull a wide-ish
    # window (limit=2000) which is plenty for V0 traffic; the existing
    # ThemeEventStore has no by-ticker index so we scan in process.
    ticker_match = slug.upper()
    all_events = await default_theme_event_store.list_all(limit=2000)
    return [e for e in all_events if any(t.upper() == ticker_match for t in (e.tickers or []))]


def _parse_day(s: str | None) -> float | None:
    """Parse a ``YYYY-MM-DD`` string into a POSIX timestamp at UTC midnight."""
    if not s:
        return None
    try:
        from datetime import datetime as _dt

        dt = _dt.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid date '{s}', expected YYYY-MM-DD"
        ) from exc


@router.get("/subjects/{subject_id}/events")
async def list_subject_events(
    subject_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """ThemeEvents narrowed to one Subject's lens.

    Optional ``date_from`` / ``date_to`` are inclusive day boundaries in
    UTC; they filter on ``event_ts`` (when the real-world event happened,
    not when the agent ingested it).
    """
    ss = await _get_subject_store()
    subj = await ss.get_subject(subject_id)
    if subj is None:
        raise HTTPException(status_code=404, detail="subject not found")

    events = await _events_for_subject(subj)
    lo = _parse_day(date_from)
    hi = _parse_day(date_to)
    if hi is not None:
        hi += 86400.0  # make `date_to` inclusive of the whole day
    if lo is not None or hi is not None:
        events = [
            e for e in events
            if (lo is None or e.event_ts >= lo) and (hi is None or e.event_ts < hi)
        ]
    return {
        "subject_id": subject_id,
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@router.get("/subjects/{subject_id}/versions/{version_no}/graph")
async def get_subject_version_graph(
    subject_id: str, version_no: int, depth: int = 1
) -> dict[str, Any]:
    """Reconstructed graph at the version's snapshot, anchored on the
    Subject's target_entity_id with a 1-hop neighborhood by default."""
    subj, target = await _resolve_version(subject_id, version_no)
    graph = await _get_store()

    current_state = {
        "entities": dict(graph.index.by_id),
        "relations": dict(graph.index.relations_by_id),
    }
    state = await graph.snapshots.reconstruct_state(current_state, target.snapshot_to)

    out = _anchor_neighborhood(
        entities=state["entities"],
        relations=state["relations"],
        anchor=subj.target_entity_id,
        depth=depth,
    )
    out["meta"].update(
        {
            "snapshot_version": target.snapshot_to,
            "subject_version": version_no,
            "subject_id": subject_id,
            "subject_type": subj.type,
        }
    )
    return out


@router.post("/subjects/{subject_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def post_subject_run(
    subject_id: str, body: SubjectRunRequest | None = None
) -> dict[str, Any]:
    """Kick off a new analysis pass on this Subject.

    Returns 202 with the freshly-created pending SubjectVersion.
    Returns 409 if another run is already in flight for this Subject.
    Returns 404 if the Subject does not exist.

    To eliminate the race window between "is a run in flight?" and the
    background task actually acquiring the lock, the request handler
    acquires the lock SYNCHRONOUSLY (raising 409 on contention) and the
    spawned task is the one that releases it on completion.
    """
    body = body or SubjectRunRequest()
    ss = await _get_subject_store()
    subj = await ss.get_subject(subject_id)
    if subj is None:
        raise HTTPException(status_code=404, detail="subject not found")

    graph = await _get_store()
    client = _build_deepseek_client()

    # Atomic lock acquire — raises if already held by another in-flight run.
    lock = ss._lock_for(subject_id)
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="another analysis run is already in flight for this subject",
        )
    await lock.acquire()

    # Persist the pending row while we still hold the request context, so
    # the immediate GET that the client may do after a 202 reflects the
    # new version_no with status=running.
    try:
        pending = await prepare_subject_run(
            subject=subj,
            subject_store=ss,
            graph_store=graph,
            triggered_by=body.triggered_by,  # type: ignore[arg-type]
            task_override=body.task_override,
        )
    except Exception:
        lock.release()
        raise

    async def _execute() -> None:
        try:
            await finish_subject_run(
                pending=pending,
                subject_store=ss,
                graph_store=graph,
                client=client,
                max_turns=body.max_turns,
            )
        except SubjectLockBusy:
            return
        except Exception:
            # finish_subject_run already wrote status=failed before re-raising.
            return
        finally:
            lock.release()

    task = asyncio.create_task(_execute())
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)

    return {
        "subject_id": subject_id,
        "status": "accepted",
        "pending": _version_to_dict(pending),
    }


# Module-level set so background tasks survive event-loop GC until done.
_pending_tasks: set[asyncio.Task] = set()
