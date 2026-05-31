from __future__ import annotations

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.persistence import default_state_store
from shinkai_api.research.models import (
    CandidateCompany,
    Claim,
    CompanyDossier,
    Evidence,
    ResearchTask,
    RunResearchState,
    SourceRef,
)


class InMemoryResearchStore:
    def __init__(self) -> None:
        self._sources: dict[str, SourceRef] = {}
        self._evidence: dict[str, Evidence] = {}
        self._claims: dict[str, Claim] = {}
        self._candidates: dict[str, CandidateCompany] = {}
        self._dossiers: dict[str, CompanyDossier] = {}
        self._tasks: dict[str, ResearchTask] = {}
        self._lock = LoopBoundLock()
        self._loaded = False

    async def upsert_source(self, source: SourceRef) -> SourceRef:
        async with self._lock.get():
            await self._ensure_loaded()
            self._sources[source.source_id] = source
            await self._persist("research_sources", self._sources)
            return source

    async def upsert_evidence(self, evidence: Evidence) -> Evidence:
        async with self._lock.get():
            await self._ensure_loaded()
            self._evidence[evidence.evidence_id] = evidence
            await self._persist("research_evidence", self._evidence)
            return evidence

    async def upsert_claim(self, claim: Claim) -> Claim:
        async with self._lock.get():
            await self._ensure_loaded()
            self._claims[claim.claim_id] = claim
            await self._persist("research_claims", self._claims)
            return claim

    async def upsert_candidate(self, candidate: CandidateCompany) -> CandidateCompany:
        async with self._lock.get():
            await self._ensure_loaded()
            self._candidates[candidate.candidate_id] = candidate
            await self._persist("research_candidates", self._candidates)
            return candidate

    async def upsert_dossier(self, dossier: CompanyDossier) -> CompanyDossier:
        async with self._lock.get():
            await self._ensure_loaded()
            self._dossiers[dossier.dossier_id] = dossier
            await self._persist("research_dossiers", self._dossiers)
            return dossier

    async def upsert_task(self, task: ResearchTask) -> ResearchTask:
        async with self._lock.get():
            await self._ensure_loaded()
            self._tasks[task.task_id] = task
            await self._persist("research_tasks", self._tasks)
            return task

    async def get_run_state(self, run_id: str) -> RunResearchState:
        async with self._lock.get():
            await self._ensure_loaded()
            return RunResearchState(
                run_id=run_id,
                sources=sorted(
                    [source for source in self._sources.values() if _has_run(source, run_id)],
                    key=lambda source: source.accessed_at,
                ),
                evidence=sorted(
                    [evidence for evidence in self._evidence.values() if evidence.run_id == run_id],
                    key=lambda evidence: evidence.extracted_at,
                ),
                claims=sorted(
                    [claim for claim in self._claims.values() if claim.run_id == run_id],
                    key=lambda claim: claim.claim_id,
                ),
                candidates=sorted(
                    [
                        candidate
                        for candidate in self._candidates.values()
                        if candidate.run_id == run_id
                    ],
                    key=lambda candidate: candidate.candidate_id,
                ),
                dossiers=sorted(
                    [
                        dossier
                        for dossier in self._dossiers.values()
                        if dossier.run_id == run_id
                    ],
                    key=lambda dossier: dossier.dossier_id,
                ),
                tasks=sorted(
                    [task for task in self._tasks.values() if task.run_id == run_id],
                    key=lambda task: task.created_at,
                ),
            )

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_state_store.load()
        self._sources = _load_models(state.get("research_sources", {}), SourceRef)
        self._evidence = _load_models(state.get("research_evidence", {}), Evidence)
        self._claims = _load_models(state.get("research_claims", {}), Claim)
        self._candidates = _load_models(
            state.get("research_candidates", {}),
            CandidateCompany,
        )
        self._dossiers = _load_models(state.get("research_dossiers", {}), CompanyDossier)
        self._tasks = _load_models(state.get("research_tasks", {}), ResearchTask)
        self._loaded = True

    async def _persist(self, section: str, values: dict) -> None:
        await default_state_store.save_section(
            section,
            {
                item_id: item.model_dump(mode="json")
                for item_id, item in values.items()
            },
        )


def _load_models(payload: object, model_class):
    if not isinstance(payload, dict):
        return {}
    return {
        item_id: model_class.model_validate(item)
        for item_id, item in payload.items()
        if isinstance(item, dict)
    }


def _has_run(source: SourceRef, run_id: str) -> bool:
    return source.metadata.get("run_id") == run_id


default_research_store = InMemoryResearchStore()
