from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from shinkai_api.eval import build_eval_report
from shinkai_api.graph import default_graph_store
from shinkai_api.research import default_research_store
from shinkai_api.results import PublishedResult, build_published_result
from shinkai_api.runs import Run, default_run_store

router = APIRouter(prefix="/results", tags=["results"])
run_result_router = APIRouter(prefix="/runs", tags=["results"])


@router.get("", response_model=list[PublishedResult])
async def list_results() -> list[PublishedResult]:
    runs = await default_run_store.list()
    completed_runs = [run for run in runs if run.status == "completed"]
    return [await _build_result(run) for run in completed_runs[:20]]


@run_result_router.get("/{run_id}/result", response_model=PublishedResult)
async def get_run_result(run_id: str) -> PublishedResult:
    return await _build_result_by_id(run_id)


@router.get("/runs/{run_id}")
async def get_result_redirect(run_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/api/v1/runs/{run_id}/result", status_code=308)


async def _build_result_by_id(run_id: str) -> PublishedResult:
    try:
        run = await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return await _build_result(run)


async def _build_result(run: Run) -> PublishedResult:
    research = await default_research_store.get_run_state(run.id)
    eval_report = None
    try:
        graph = await default_graph_store.get_by_run(run.id)
        eval_report = build_eval_report(run, graph)
    except KeyError:
        pass
    return build_published_result(run, research, eval_report)
