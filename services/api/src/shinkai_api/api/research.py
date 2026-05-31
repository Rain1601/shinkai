from fastapi import APIRouter, HTTPException

from shinkai_api.research import RunResearchState, default_research_store
from shinkai_api.runs import default_run_store

router = APIRouter(prefix="/runs", tags=["research"])


@router.get("/{run_id}/research", response_model=RunResearchState)
async def get_run_research(run_id: str) -> RunResearchState:
    try:
        await default_run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return await default_research_store.get_run_state(run_id)
