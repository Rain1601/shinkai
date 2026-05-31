from __future__ import annotations

from shinkai_api.checkpoints.models import Checkpoint, CheckpointDecision


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    async def list_by_run(self, run_id: str) -> list[Checkpoint]:
        return [
            checkpoint for checkpoint in self._checkpoints.values() if checkpoint.run_id == run_id
        ]

    async def get(self, checkpoint_id: str) -> Checkpoint:
        return self._checkpoints[checkpoint_id]

    async def release(self, checkpoint_id: str, decision: CheckpointDecision) -> Checkpoint:
        checkpoint = self._checkpoints[checkpoint_id]
        checkpoint.decision = decision
        checkpoint.status = "released"
        return checkpoint


default_checkpoint_store = InMemoryCheckpointStore()
