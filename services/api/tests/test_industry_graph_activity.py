"""Tests for the Run-event → Subject attribution layer that drives the
``GET /activity`` and ``GET /subjects/{id}/activity`` endpoints.

The merge plan calls these out as the "load-bearing piece": the rule
table they encode is what every downstream UI tab consumes. Each rule
gets its own test so an accidental regression is loud.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shinkai_api.industry_graph.activity import (
    ANALYTICAL_EVENT_TYPES,
    build_activity_rows,
    resolve_affected_subjects,
)
from shinkai_api.industry_graph.subjects import Subject
from shinkai_api.runs.models import Run
from shinkai_api.schemas.events import AgentEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _co_subject(slug: str, ticker: str) -> Subject:
    now = _now()
    return Subject(
        id=f"subj:{slug}",
        type="company",
        display_name=ticker,
        target_entity_id=f"co:{ticker}",
        created_at=now,
        updated_at=now,
    )


def _theme_subject(slug: str, target: str) -> Subject:
    now = _now()
    return Subject(
        id=f"subj:{slug}",
        type="theme",
        display_name=slug.upper(),
        target_entity_id=target,
        created_at=now,
        updated_at=now,
    )


def _run(anchor: str, events: list[AgentEvent]) -> Run:
    return Run(id="run-1", mode="mode_b_narrative", anchor=anchor, events=events)


def _ev(event_type: str, data: dict, ts: float = 1.0) -> AgentEvent:
    return AgentEvent(type=event_type, data=data, ts=ts)  # type: ignore[arg-type]


# ── attribution rules ───────────────────────────────────────────────────
def test_dossier_attributed_via_ticker() -> None:
    subs = [_co_subject("nvda", "NVDA"), _co_subject("aapl", "AAPL")]
    run = _run(
        anchor="AI infrastructure",
        events=[
            _ev("company_dossier_created", {"ticker": "NVDA", "name": "NVIDIA"}, ts=10),
            _ev("company_dossier_created", {"ticker": "AAPL", "name": "Apple"}, ts=11),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert len(attribution) == 2
    # Each dossier maps to exactly one company subject.
    all_subjects = {sid for s in attribution.values() for sid in s}
    assert all_subjects == {"subj:nvda", "subj:aapl"}


def test_deep_analysis_attributed_via_ticker() -> None:
    subs = [_co_subject("nvda", "NVDA")]
    run = _run(
        anchor="AI infra",
        events=[
            _ev(
                "company_deep_analysis_completed",
                {"ticker": "NVDA", "status": "completed"},
            ),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert next(iter(attribution.values())) == {"subj:nvda"}


def test_judgment_attributed_via_theme_key() -> None:
    """judgment_created has no ticker — falls back to theme_key(run.anchor)."""
    subs = [_theme_subject("ai-infrastructure", "st:ai_infra")]
    run = _run(
        anchor="AI Infrastructure",
        events=[
            _ev(
                "judgment_created",
                {"layer": "memory", "judgment": "supported", "confidence": 0.82},
            ),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert next(iter(attribution.values())) == {"subj:ai-infrastructure"}


def test_judgment_without_matching_theme_dropped() -> None:
    """No Theme Subject for this anchor → judgment event is dropped."""
    subs = [_theme_subject("hbm", "st:hbm")]
    run = _run(
        anchor="Quantum computing supply chain",
        events=[
            _ev("judgment_created", {"layer": "fab", "judgment": "supported"}),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert attribution == {}


def test_unknown_ticker_dropped() -> None:
    """Dossier mentioning a ticker no Subject covers → dropped."""
    subs = [_co_subject("nvda", "NVDA")]
    run = _run(
        anchor="random theme",
        events=[
            _ev("company_dossier_created", {"ticker": "XYZ", "name": "Mystery"}),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert attribution == {}


def test_non_analytical_events_excluded() -> None:
    subs = [_co_subject("nvda", "NVDA")]
    run = _run(
        anchor="anything",
        events=[
            _ev("frontier_selected", {"ticker": "NVDA"}),
            _ev("claim_created", {"ticker": "NVDA"}),
            _ev("candidate_scored", {"ticker": "NVDA"}),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert attribution == {}
    # Belt-and-suspenders: every analytical type IS in the set.
    assert {
        "company_dossier_created",
        "company_deep_analysis_completed",
        "judgment_created",
    } <= ANALYTICAL_EVENT_TYPES


def test_ticker_case_and_whitespace_normalized() -> None:
    subs = [_co_subject("nvda", "NVDA")]
    run = _run(
        anchor="x",
        events=[
            _ev("company_dossier_created", {"ticker": "  nvda  ", "name": "NVIDIA"}),
        ],
    )
    by_t, by_th = _index(subs)
    attribution = resolve_affected_subjects(run, by_ticker=by_t, by_theme_slug=by_th)
    assert next(iter(attribution.values())) == {"subj:nvda"}


# ── build_activity_rows behaviour ───────────────────────────────────────
def test_build_rows_emits_one_per_subject_touched() -> None:
    """One event that touches BOTH a Company subject (via ticker) and a
    Theme subject (no — judgments are theme-only; dossier is ticker-only)
    yields one row. The fan-out test for shared events lives below.
    """
    subs = [_co_subject("nvda", "NVDA"), _theme_subject("hbm", "st:hbm")]
    run = _run(
        anchor="HBM",
        events=[
            _ev(
                "company_dossier_created",
                {"ticker": "NVDA", "name": "NVIDIA", "decision": "queue_mode_a"},
                ts=100,
            ),
            _ev(
                "judgment_created",
                {"layer": "memory", "judgment": "supported", "confidence": 0.9},
                ts=200,
            ),
        ],
    )
    rows = build_activity_rows([run], subs)
    # Two events, each attributed to one subject → two rows.
    assert len(rows) == 2
    by_type = {r["type"]: r for r in rows}
    assert by_type["company_dossier_created"]["subject_id"] == "subj:nvda"
    assert by_type["judgment_created"]["subject_id"] == "subj:hbm"
    # Newest first.
    assert rows[0]["ts"] >= rows[1]["ts"]


def test_build_rows_filter_to_one_subject() -> None:
    subs = [_co_subject("nvda", "NVDA"), _co_subject("aapl", "AAPL")]
    run = _run(
        anchor="x",
        events=[
            _ev("company_dossier_created", {"ticker": "NVDA", "name": "NVIDIA"}),
            _ev("company_dossier_created", {"ticker": "AAPL", "name": "Apple"}),
        ],
    )
    rows_all = build_activity_rows([run], subs)
    rows_nvda = build_activity_rows([run], subs, subject_filter="subj:nvda")
    assert len(rows_all) == 2
    assert len(rows_nvda) == 1
    assert rows_nvda[0]["subject_id"] == "subj:nvda"


def test_build_rows_summary_strings() -> None:
    subs = [_co_subject("nvda", "NVDA"), _theme_subject("hbm", "st:hbm")]
    run = _run(
        anchor="HBM",
        events=[
            _ev(
                "company_dossier_created",
                {"ticker": "NVDA", "name": "NVIDIA", "decision": "queue_mode_a"},
            ),
            _ev(
                "company_deep_analysis_completed",
                {"ticker": "NVDA", "name": "NVIDIA", "status": "completed"},
            ),
            _ev(
                "judgment_created",
                {"layer": "memory", "judgment": "supported", "confidence": 0.91},
            ),
        ],
    )
    rows = build_activity_rows([run], subs)
    summaries = {r["type"]: r["summary"] for r in rows}
    assert summaries["company_dossier_created"] == "NVIDIA · queue_mode_a"
    assert summaries["company_deep_analysis_completed"] == "NVIDIA · completed"
    assert "memory" in summaries["judgment_created"]
    assert "supported" in summaries["judgment_created"]


def test_build_rows_limit_caps_output() -> None:
    subs = [_co_subject("nvda", "NVDA")]
    events = [
        _ev("company_dossier_created", {"ticker": "NVDA", "name": "n"}, ts=float(i))
        for i in range(80)
    ]
    rows = build_activity_rows([_run("x", events)], subs, limit=25)
    assert len(rows) == 25
    # Sorted newest first → first row should be ts=79.
    assert rows[0]["ts"] == 79.0


def test_build_rows_skips_runs_with_no_attribution() -> None:
    """Runs whose events match NO subject pay no per-event cost downstream."""
    subs = [_co_subject("nvda", "NVDA")]
    run1 = _run(
        anchor="x",
        events=[_ev("company_dossier_created", {"ticker": "XYZ"})],
    )
    run2 = _run(
        anchor="y",
        events=[_ev("company_dossier_created", {"ticker": "NVDA"})],
    )
    rows = build_activity_rows([run1, run2], subs)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"  # both runs share the id; just sanity


# ── helpers ─────────────────────────────────────────────────────────────
def _index(subs: list[Subject]):
    from shinkai_api.industry_graph.activity import _index_subjects

    return _index_subjects(subs)


# ── Theme members resolver (api._theme_members) ─────────────────────────
def test_theme_members_explicit_link_wins() -> None:
    from shinkai_api.api.industry_graph import _theme_members

    theme = _theme_subject("hbm", "st:hbm")
    entities = {
        "co:SK": {
            "id": "co:SK", "kind": "Company", "labels": ["SK Hynix"],
            "facets": {"subtheme": ["st:hbm"]},
        },
        "co:MU": {
            "id": "co:MU", "kind": "Company", "labels": ["Micron"],
            "facets": {"chain_layers": ["HBM 内存"]},  # would match fallback
        },
        "co:OTHER": {
            "id": "co:OTHER", "kind": "Company", "labels": ["Other"],
            "facets": {},
        },
    }
    company_subjects_by_target = {"co:SK": "subj:sk"}
    members = _theme_members(theme, entities, company_subjects_by_target)
    # Explicit hit wins → only SK Hynix; Micron is ignored even though its
    # chain_layers would have matched the fallback.
    assert [m["id"] for m in members] == ["co:SK"]
    assert members[0]["has_subject_id"] == "subj:sk"


def test_theme_members_chain_layers_fallback() -> None:
    from shinkai_api.api.industry_graph import _theme_members

    theme = _theme_subject("hbm", "st:hbm")
    entities = {
        "co:SK": {
            "id": "co:SK", "kind": "Company", "labels": ["SK Hynix"],
            "facets": {"chain_layers": ["HBM 内存 (High-Bandwidth Memory)"]},
        },
        "co:MU": {
            "id": "co:MU", "kind": "Company", "labels": ["Micron"],
            "facets": {"chain_layers": ["hbm production"]},  # case-insensitive
        },
        "co:OTHER": {
            "id": "co:OTHER", "kind": "Company", "labels": ["Other"],
            "facets": {"chain_layers": ["Foundry"]},
        },
    }
    members = _theme_members(theme, entities, {})
    assert sorted(m["id"] for m in members) == ["co:MU", "co:SK"]
    # Alphabetically by label.
    assert [m["label"] for m in members] == ["Micron", "SK Hynix"]
    # No Subject record for these companies in this test fixture.
    assert all(m["has_subject_id"] is None for m in members)


def test_theme_members_excludes_deprecated_and_non_company() -> None:
    from shinkai_api.api.industry_graph import _theme_members

    theme = _theme_subject("hbm", "st:hbm")
    entities = {
        "co:SK": {
            "id": "co:SK", "kind": "Company", "labels": ["SK Hynix"],
            "facets": {"chain_layers": ["HBM"]},
            "deprecated_at": "2026-06-21T00:00:00Z",  # deprecated → skipped
        },
        "co:MU": {
            "id": "co:MU", "kind": "Company", "labels": ["Micron"],
            "facets": {"chain_layers": ["HBM"]},
        },
        "st:hbm": {
            "id": "st:hbm", "kind": "SubTheme", "labels": ["HBM"],
            "facets": {},  # SubTheme itself: never a member
        },
    }
    members = _theme_members(theme, entities, {})
    assert [m["id"] for m in members] == ["co:MU"]
