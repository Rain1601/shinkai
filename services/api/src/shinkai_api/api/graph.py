from fastapi import APIRouter, HTTPException

from shinkai_api.graph import Graph, default_graph_store

router = APIRouter(prefix="/runs", tags=["graph"])


@router.get("/{run_id}/graph", response_model=Graph)
async def get_graph(run_id: str) -> Graph:
    try:
        return await default_graph_store.get_by_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="graph not found") from exc
