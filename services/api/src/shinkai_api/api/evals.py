from fastapi import APIRouter, HTTPException

from shinkai_api.eval import EvalReport, build_eval_report
from shinkai_api.graph import default_graph_store
from shinkai_api.runs import default_run_store

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/runs/{run_id}", response_model=EvalReport)
async def get_eval_report(run_id: str) -> EvalReport:
    try:
        run = await default_run_store.get(run_id)
        graph = await default_graph_store.get_by_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run or graph not found") from exc
    return build_eval_report(run, graph)
