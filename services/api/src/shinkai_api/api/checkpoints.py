from fastapi import APIRouter, Depends, HTTPException

from shinkai_api.checkpoints import Checkpoint, CheckpointDecision, default_checkpoint_store
from shinkai_api.core.auth import require_admin

router = APIRouter(tags=["checkpoints"])


@router.get("/runs/{run_id}/checkpoints", response_model=list[Checkpoint])
async def list_checkpoints(run_id: str) -> list[Checkpoint]:
    return await default_checkpoint_store.list_by_run(run_id)


@router.get("/checkpoints/{checkpoint_id}", response_model=Checkpoint)
async def get_checkpoint(checkpoint_id: str) -> Checkpoint:
    try:
        return await default_checkpoint_store.get(checkpoint_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="checkpoint not found") from exc


@router.post(
    "/checkpoints/{checkpoint_id}/release",
    response_model=Checkpoint,
    dependencies=[Depends(require_admin)],
)
async def release_checkpoint(
    checkpoint_id: str,
    decision: CheckpointDecision,
) -> Checkpoint:
    try:
        return await default_checkpoint_store.release(checkpoint_id, decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="checkpoint not found") from exc
