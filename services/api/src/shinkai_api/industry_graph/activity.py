"""Resolve which Subjects a historical Run touched.

This is the load-bearing piece for the `/live` → `/industry-graph` merge:
  - `GET /subjects/{id}/activity` shows the analytical Run events that
    historically touched this Subject.
  - `GET /activity` shows the same kind of feed but cross-subject, so the
    list page can offer the Activity tab as a drop-in replacement for
    `/live`'s right-rail "Analyses" pane.

Attribution rules (mirror the V0 plan's Stage 1 contract):
  1. ``company_dossier_created`` and ``company_deep_analysis_completed``
     carry ``data.ticker``. We match that ticker to a Company Subject by
     comparing ``Subject.target_entity_id`` against ``co:<TICKER>``.
  2. ``judgment_created`` does not carry a company id — it is layer-scoped
     within a Mode B narrative. We attribute it to Theme Subjects whose
     id slug equals ``theme_key(Run.anchor)``. Best effort; the trade-off
     is flagged in the plan.

Events outside this small analytical set are ignored. We intentionally
do NOT widen the set in V0: spamming the Activity feed with low-signal
events (frontier_selected, claim_created, etc.) defeats the purpose.

The dispatcher is intentionally side-effect-free and the scans are
naive O(runs × events). With <100 Runs in a normal local store the
latency is comfortably sub-100ms; caching lands in a future iteration
when the count crosses ~500.
"""

from __future__ import annotations

from typing import Any

from shinkai_api.runs.models import Run
from shinkai_api.runs.themes import theme_key

from .subjects import Subject

# Mirrors the ANALYSIS_TYPES set in apps/web/app/live/page.tsx. Surfacing
# this server-side means the frontend can drop its local constant in a
# follow-up cleanup and trust the API to filter.
ANALYTICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "company_dossier_created",
        "company_deep_analysis_completed",
        "judgment_created",
    }
)


def _ticker_from_target(target_entity_id: str | None) -> str | None:
    """``co:NVDA`` → ``NVDA``. Returns None for non-Company targets."""
    if not target_entity_id or not target_entity_id.startswith("co:"):
        return None
    body = target_entity_id.split(":", 1)[1]
    return body.upper().strip()


def _index_subjects(
    subjects: list[Subject],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build two lookup tables for attribution:
    - ``ticker → subject_id`` for Company subjects (keyed by upper-case ticker)
    - ``theme_id_slug → subject_id`` for Theme subjects (slug derived from
      the part after ``subj:`` in the Subject id, matched against
      ``theme_key(run.anchor)``).
    """
    by_ticker: dict[str, str] = {}
    by_theme_slug: dict[str, str] = {}
    for s in subjects:
        if s.type == "company":
            t = _ticker_from_target(s.target_entity_id)
            if t:
                by_ticker[t] = s.id
        elif s.type == "theme":
            slug = s.id.split(":", 1)[1] if ":" in s.id else s.id
            by_theme_slug[slug] = s.id
    return by_ticker, by_theme_slug


def resolve_affected_subjects(
    run: Run,
    *,
    by_ticker: dict[str, str],
    by_theme_slug: dict[str, str],
) -> dict[str, set[str]]:
    """For one Run, return ``{event_id → set[subject_id]}``.

    Each analytical event is mapped to zero, one or many subjects:
    - dossier / deep_analysis events with ``data.ticker`` map to the
      matching Company Subject when one exists.
    - judgment events map to the Theme Subject whose slug matches
      ``theme_key(run.anchor)`` when one exists.
    Events that don't match any rule are omitted from the result.
    """
    out: dict[str, set[str]] = {}
    anchor_slug = theme_key(run.anchor)
    theme_subj_id = by_theme_slug.get(anchor_slug)
    for ev in run.events:
        if ev.type not in ANALYTICAL_EVENT_TYPES:
            continue
        touched: set[str] = set()
        if ev.type == "judgment_created":
            if theme_subj_id:
                touched.add(theme_subj_id)
        else:
            raw_ticker = ev.data.get("ticker") if isinstance(ev.data, dict) else None
            if isinstance(raw_ticker, str):
                subj_id = by_ticker.get(raw_ticker.upper().strip())
                if subj_id:
                    touched.add(subj_id)
        if touched:
            out[ev.event_id] = touched
    return out


def _summarize_event(ev_type: str, data: dict[str, Any]) -> str:
    """A one-liner per event type for the feed row body.

    Kept small on purpose — the row is a glanceable summary; the Activity
    tab is not where you read a full dossier.
    """
    if not isinstance(data, dict):
        return ""
    if ev_type == "company_dossier_created":
        name = data.get("name") or data.get("ticker") or ""
        decision = data.get("decision") or ""
        return f"{name} · {decision}".strip(" ·")
    if ev_type == "company_deep_analysis_completed":
        name = data.get("name") or data.get("ticker") or ""
        status = data.get("status") or ""
        return f"{name} · {status}".strip(" ·")
    if ev_type == "judgment_created":
        layer = data.get("layer") or ""
        judgment = data.get("judgment") or ""
        confidence = data.get("confidence")
        tail = f" · c{confidence}" if isinstance(confidence, int | float) else ""
        return f"{layer} → {judgment}{tail}".strip(" ·→")
    return ""


def build_activity_rows(
    runs: list[Run],
    subjects: list[Subject],
    *,
    subject_filter: str | None = None,
    limit: int = 60,
) -> list[dict[str, Any]]:
    """Walk every Run and yield analytical-event rows, optionally
    restricted to a specific subject_id.

    Each row carries everything the React feed needs in one shot:
    ``event_id``, ``run_id``, ``type``, ``ts``, ``summary``, ``subject_id``,
    plus ``data`` for the expandable detail view.

    Rows are sorted by ``ts`` desc and capped at ``limit``.
    """
    by_ticker, by_theme_slug = _index_subjects(subjects)
    rows: list[dict[str, Any]] = []
    for run in runs:
        attribution = resolve_affected_subjects(
            run, by_ticker=by_ticker, by_theme_slug=by_theme_slug
        )
        if not attribution:
            continue
        for ev in run.events:
            touched = attribution.get(ev.event_id)
            if not touched:
                continue
            if subject_filter is not None and subject_filter not in touched:
                continue
            summary = _summarize_event(ev.type, ev.data)
            # Emit one row per (event, subject) so a single dossier that
            # touches both NVDA Company and HBM Theme shows up under both.
            for subject_id in sorted(touched):
                rows.append(
                    {
                        "event_id": ev.event_id,
                        "run_id": run.id,
                        "run_anchor": run.anchor,
                        "type": ev.type,
                        "ts": ev.ts,
                        "summary": summary,
                        "subject_id": subject_id,
                        "data": ev.data,
                    }
                )
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]


__all__ = [
    "ANALYTICAL_EVENT_TYPES",
    "build_activity_rows",
    "resolve_affected_subjects",
]
