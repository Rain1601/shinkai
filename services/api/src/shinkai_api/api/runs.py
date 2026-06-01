import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shinkai_api.core.auth import require_admin
from shinkai_api.graph import default_graph_store
from shinkai_api.research import default_research_store
from shinkai_api.research.models import (
    Claim,
    Evidence,
    Hypothesis,
    SourceRef,
)
from shinkai_api.runs import Run, RunCreate, default_run_store
from shinkai_api.runs.executor import default_run_executor
from shinkai_api.schemas.events import AgentEvent

router = APIRouter(prefix="/runs", tags=["runs"])
TERMINAL_STATUSES = {"completed", "failed", "aborted"}


@router.post("", response_model=Run, dependencies=[Depends(require_admin)])
async def create_run(payload: RunCreate) -> Run:
    run = await default_run_store.create(payload)
    graph = await default_graph_store.create_for_run(run)
    run = await default_run_store.set_graph_id(run.id, graph.graph_id)
    event = AgentEvent(
        type="run_start", run_id=run.id, data={"mode": run.mode, "anchor": run.anchor}
    )
    await default_run_store.append_event(run.id, event)
    return run


@router.get("", response_model=list[Run])
async def list_runs() -> list[Run]:
    return await default_run_store.list()


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str) -> Run:
    try:
        return await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.post("/{run_id}/start", response_model=Run, dependencies=[Depends(require_admin)])
async def start_run(run_id: str) -> Run:
    try:
        return await default_run_executor.start(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.post("/{run_id}/pause", response_model=Run, dependencies=[Depends(require_admin)])
async def pause_run(run_id: str) -> Run:
    try:
        run = await default_run_store.get(run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        return await default_run_store.set_status(run_id, "paused")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.post("/{run_id}/resume", response_model=Run, dependencies=[Depends(require_admin)])
async def resume_run(run_id: str) -> Run:
    try:
        run = await default_run_store.get(run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        return await default_run_store.set_status(run_id, "running")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.post("/{run_id}/abort", response_model=Run, dependencies=[Depends(require_admin)])
async def abort_run(run_id: str) -> Run:
    try:
        return await default_run_executor.abort(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


class HumanInjection(BaseModel):
    note: str
    intent: str = "guidance"


@router.post(
    "/{run_id}/inject",
    response_model=Run,
    dependencies=[Depends(require_admin)],
)
async def inject_into_run(run_id: str, payload: HumanInjection) -> Run:
    """Append a human-authored guidance event into the run's event log.

    The harness reads these from the run's event history; injections from a
    paused state are picked up when the run resumes.
    """
    try:
        run = await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    if run.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="run is terminal")
    note = payload.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="note must not be empty")
    event = AgentEvent(
        type="human_injection",
        run_id=run_id,
        data={
            "intent": payload.intent,
            "note": note,
        },
    )
    await default_run_store.append_event(run_id, event)
    return await default_run_store.get(run_id)


class CheckpointDecision(BaseModel):
    decision: str  # "approve" | "reject" | "modify"
    note: str = ""


@router.post(
    "/{run_id}/checkpoint",
    response_model=Run,
    dependencies=[Depends(require_admin)],
)
async def resolve_checkpoint(run_id: str, payload: CheckpointDecision) -> Run:
    """Resolve an awaiting checkpoint by approving, rejecting, or sending guidance."""
    try:
        run = await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    if run.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="run is terminal")
    if payload.decision not in {"approve", "reject", "modify"}:
        raise HTTPException(
            status_code=400,
            detail="decision must be one of: approve, reject, modify",
        )
    event = AgentEvent(
        type="checkpoint_released",
        run_id=run_id,
        data={
            "source": "human_review",
            "decision": payload.decision,
            "note": payload.note,
            "previous_status": run.status,
        },
    )
    await default_run_store.append_event(run_id, event)
    if payload.decision == "reject":
        return await default_run_executor.abort(run_id)
    if run.status == "awaiting_checkpoint" or run.status == "paused":
        return await default_run_store.set_status(run_id, "running")
    return await default_run_store.get(run_id)


@router.get("/{run_id}/hypotheses", response_model=list[Hypothesis])
async def list_hypotheses(run_id: str) -> list[Hypothesis]:
    try:
        await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return await default_research_store.get_hypotheses_by_run(run_id)


class ReasoningClaim(BaseModel):
    """A claim plus its resolved supporting / contradicting evidence records."""

    claim: Claim
    supporting_evidence: list[Evidence] = []
    contradicting_evidence: list[Evidence] = []


class ReasoningHypothesis(BaseModel):
    hypothesis: Hypothesis
    claims: list[ReasoningClaim] = []
    orphan: bool = False


class ReasoningTree(BaseModel):
    run_id: str
    hypotheses: list[ReasoningHypothesis]
    orphan_claims: list[ReasoningClaim]
    sources: dict[str, SourceRef]


@router.get("/{run_id}/reasoning-tree", response_model=ReasoningTree)
async def reasoning_tree(run_id: str) -> ReasoningTree:
    """Return the full reasoning structure for a run in one call.

    The shape is Hypothesis -> Claim -> Evidence -> Source. Claims that do
    not carry a ``hypothesis_id`` (typically older runs or non-layer claims)
    are returned under ``orphan_claims`` so the client can still surface
    them. ``sources`` is a flat map keyed by ``source_id`` so the client
    does not need a second lookup per evidence row.
    """
    try:
        await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    state = await default_research_store.get_run_state(run_id)
    hypotheses = await default_research_store.get_hypotheses_by_run(run_id)

    evidence_by_id = {ev.evidence_id: ev for ev in state.evidence}
    sources_by_id = {src.source_id: src for src in state.sources}

    def _resolve(claim: Claim) -> ReasoningClaim:
        supporting = [
            evidence_by_id[eid]
            for eid in claim.supporting_evidence_ids
            if eid in evidence_by_id
        ]
        contradicting = [
            evidence_by_id[eid]
            for eid in claim.contradicting_evidence_ids
            if eid in evidence_by_id
        ]
        return ReasoningClaim(
            claim=claim,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
        )

    claims_by_hypothesis: dict[str, list[Claim]] = {}
    orphan_claims: list[Claim] = []
    for claim in state.claims:
        if claim.hypothesis_id:
            claims_by_hypothesis.setdefault(claim.hypothesis_id, []).append(claim)
        else:
            orphan_claims.append(claim)

    tree_hypotheses: list[ReasoningHypothesis] = []
    for hypothesis in hypotheses:
        claims = claims_by_hypothesis.get(hypothesis.hypothesis_id, [])
        tree_hypotheses.append(
            ReasoningHypothesis(
                hypothesis=hypothesis,
                claims=[_resolve(claim) for claim in claims],
            )
        )

    return ReasoningTree(
        run_id=run_id,
        hypotheses=tree_hypotheses,
        orphan_claims=[_resolve(claim) for claim in orphan_claims],
        sources=sources_by_id,
    )


@router.get("/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    try:
        await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    async def event_stream():
        cursor = 0
        while True:
            run = await default_run_store.get(run_id)
            while cursor < len(run.events):
                event = run.events[cursor]
                cursor += 1
                payload = json.dumps(event.model_dump(), ensure_ascii=False)
                yield f"id: {event.event_id}\nevent: {event.type}\ndata: {payload}\n\n"
            if run.status in TERMINAL_STATUSES:
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
