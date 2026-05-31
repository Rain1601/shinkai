import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from shinkai_api.core.auth import require_admin
from shinkai_api.graph import default_graph_store
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
