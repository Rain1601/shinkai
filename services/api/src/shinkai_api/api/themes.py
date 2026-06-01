from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shinkai_api.research import default_research_store
from shinkai_api.research.models import Hypothesis
from shinkai_api.runs import Run, default_run_store
from shinkai_api.runs.themes import theme_key

router = APIRouter(prefix="/themes", tags=["themes"])


class ThemeSummary(BaseModel):
    theme_id: str
    title: str
    run_count: int
    active_hypothesis_count: int
    falsified_hypothesis_count: int
    last_activity_ts: float
    latest_run_id: str | None
    running_count: int


class ThemeRunSummary(BaseModel):
    run_id: str
    status: str
    lifecycle_stage: str
    anchor: str
    last_activity_ts: float


class ThemeDetail(BaseModel):
    theme_id: str
    title: str
    runs: list[ThemeRunSummary]
    active_hypotheses: list[Hypothesis]
    falsified_hypotheses: list[Hypothesis]
    procedural_memory: list[dict] = []
    next_reschedule: str | None = None


def _last_activity_ts(run: Run) -> float:
    timestamps = [event.ts for event in run.events if event.ts]
    return max(timestamps) if timestamps else 0.0


def _runs_by_theme(runs: list[Run]) -> dict[str, list[Run]]:
    grouped: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        grouped[theme_key(run.anchor)].append(run)
    return grouped


@router.get("", response_model=list[ThemeSummary])
async def list_themes() -> list[ThemeSummary]:
    runs = await default_run_store.list()
    grouped = _runs_by_theme(runs)
    summaries: list[ThemeSummary] = []
    for theme_id, theme_runs in grouped.items():
        sorted_runs = sorted(theme_runs, key=_last_activity_ts, reverse=True)
        latest = sorted_runs[0]
        active = 0
        falsified = 0
        for run in theme_runs:
            hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
            active += sum(1 for h in hypotheses if h.state == "active")
            falsified += sum(1 for h in hypotheses if h.state == "falsified")
        running_count = sum(
            1
            for run in theme_runs
            if run.status not in {"completed", "failed", "aborted"}
        )
        summaries.append(
            ThemeSummary(
                theme_id=theme_id,
                title=latest.anchor,
                run_count=len(theme_runs),
                active_hypothesis_count=active,
                falsified_hypothesis_count=falsified,
                last_activity_ts=_last_activity_ts(latest),
                latest_run_id=latest.id,
                running_count=running_count,
            )
        )
    summaries.sort(key=lambda s: s.last_activity_ts, reverse=True)
    return summaries


@router.get("/{theme_id}", response_model=ThemeDetail)
async def get_theme(theme_id: str) -> ThemeDetail:
    runs = await default_run_store.list()
    grouped = _runs_by_theme(runs)
    if theme_id not in grouped:
        raise HTTPException(status_code=404, detail="theme not found")
    theme_runs = sorted(grouped[theme_id], key=_last_activity_ts, reverse=True)
    title = theme_runs[0].anchor

    active: dict[str, Hypothesis] = {}
    falsified: dict[str, Hypothesis] = {}
    for run in theme_runs:
        hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
        for hypothesis in hypotheses:
            if hypothesis.state == "active":
                # Keep the latest run's snapshot when the same hypothesis_id
                # recurs across runs (deterministic ids ⇒ stable dedup).
                if hypothesis.hypothesis_id not in active:
                    active[hypothesis.hypothesis_id] = hypothesis
            elif hypothesis.state == "falsified":
                if hypothesis.hypothesis_id not in falsified:
                    falsified[hypothesis.hypothesis_id] = hypothesis

    return ThemeDetail(
        theme_id=theme_id,
        title=title,
        runs=[
            ThemeRunSummary(
                run_id=run.id,
                status=run.status,
                lifecycle_stage=run.lifecycle_stage,
                anchor=run.anchor,
                last_activity_ts=_last_activity_ts(run),
            )
            for run in theme_runs
        ],
        active_hypotheses=list(active.values()),
        falsified_hypotheses=list(falsified.values()),
    )
