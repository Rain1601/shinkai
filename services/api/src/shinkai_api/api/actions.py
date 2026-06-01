"""Actions surface: triggers / critics / memory / patches inbox.

This is the read-only "what does this agent KNOW HOW to do" page plus the
one writable thing — the patch decision inbox. Patches are proposed by the
harness as it reflects on a run (e.g. memory_patch_proposed); the inbox
lets a human accept / reject / modify each one.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shinkai_api.actions import default_actions_store
from shinkai_api.agent.personas import (
    AUDITOR_PROMPT,
    BUFFETT_PROMPT,
    SHORT_SELLER_PROMPT,
)
from shinkai_api.api.agent import AgentTrigger, _build_triggers
from shinkai_api.research import default_research_store
from shinkai_api.runs import default_run_store

router = APIRouter(prefix="/actions", tags=["actions"])

PATCH_TYPES = {
    "memory_patch_proposed",
    "filter_policy_patch_proposed",
    "checklist_patch_proposed",
}


class CriticPersona(BaseModel):
    key: str
    name_en: str
    name_zh: str
    prompt_text: str
    v0_rule_summary_en: str
    v0_rule_summary_zh: str
    total_verdicts: int = 0
    total_rejects: int = 0


class MemoryLayer(BaseModel):
    layer: str
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    count: int = 0
    sample: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["live", "scaffolded"] = "scaffolded"


class PatchSummary(BaseModel):
    patch_id: str
    type: str
    proposal: str
    requires_human_approval: bool = False
    run_id: str | None
    ts: float | None
    loop_index: int | None = None
    decision: Literal["pending", "accepted", "rejected", "modified"] = "pending"
    decided_at: float | None = None
    note: str = ""


class PatchDecideRequest(BaseModel):
    decision: Literal["accept", "reject", "modify"]
    note: str = ""


@router.get("/triggers", response_model=list[AgentTrigger])
async def get_triggers() -> list[AgentTrigger]:
    return _build_triggers()


@router.get("/critics", response_model=list[CriticPersona])
async def get_critics() -> list[CriticPersona]:
    runs = await default_run_store.list()
    verdicts_by_persona: dict[str, int] = {"buffett": 0, "short_seller": 0, "auditor": 0}
    rejects_by_persona: dict[str, int] = {"buffett": 0, "short_seller": 0, "auditor": 0}
    for run in runs:
        for event in run.events:
            if event.type == "critic_persona_critique":
                persona = str(event.data.get("persona", ""))
                if persona in verdicts_by_persona:
                    verdicts_by_persona[persona] += 1
                    if event.data.get("verdict") == "reject":
                        rejects_by_persona[persona] += 1

    return [
        CriticPersona(
            key="buffett",
            name_en="Buffett school",
            name_zh="巴菲特学派",
            prompt_text=BUFFETT_PROMPT,
            v0_rule_summary_en=(
                "quality_score >= 0.7 → endorse; 0.5..0.7 → concerns; "
                "< 0.5 → reject. Focus: durable moat, capital allocation."
            ),
            v0_rule_summary_zh=(
                "质量分 ≥ 0.7 支持;0.5–0.7 存疑;< 0.5 否决。关注:护城河、资本配置。"
            ),
            total_verdicts=verdicts_by_persona["buffett"],
            total_rejects=rejects_by_persona["buffett"],
        ),
        CriticPersona(
            key="short_seller",
            name_en="Short-seller",
            name_zh="做空视角",
            prompt_text=SHORT_SELLER_PROMPT,
            v0_rule_summary_en=(
                "underwater_score >= 0.7 with <2 supporting evidence → reject; "
                ">= 0.6 → concerns; else endorse."
            ),
            v0_rule_summary_zh=(
                "低覆盖度 ≥ 0.7 且支持证据 < 2 否决;≥ 0.6 存疑;否则支持。"
            ),
            total_verdicts=verdicts_by_persona["short_seller"],
            total_rejects=rejects_by_persona["short_seller"],
        ),
        CriticPersona(
            key="auditor",
            name_en="Forensic auditor",
            name_zh="审计视角",
            prompt_text=AUDITOR_PROMPT,
            v0_rule_summary_en=(
                "primary_source_count == 0 → reject; contradictions > primary → "
                "reject; primary == 1 → concerns; else endorse."
            ),
            v0_rule_summary_zh=(
                "一手来源 = 0 否决;反证多于一手来源 否决;一手 = 1 存疑;否则支持。"
            ),
            total_verdicts=verdicts_by_persona["auditor"],
            total_rejects=rejects_by_persona["auditor"],
        ),
    ]


@router.get("/memory", response_model=list[MemoryLayer])
async def get_memory() -> list[MemoryLayer]:
    runs = await default_run_store.list()

    total_events = sum(len(run.events) for run in runs)
    semantic_count = 0
    semantic_sample: list[dict[str, Any]] = []
    for run in runs:
        hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
        semantic_count += len(hypotheses)
        if not semantic_sample:
            semantic_sample = [
                {
                    "hypothesis_id": h.hypothesis_id,
                    "layer": h.layer,
                    "claim": h.claim[:120],
                    "state": h.state,
                }
                for h in hypotheses[:3]
            ]

    accepted_patches = [
        record
        for record in (await default_actions_store.list_all()).values()
        if record.decision == "accepted"
    ]

    return [
        MemoryLayer(
            layer="working",
            name_en="Working memory",
            name_zh="工作记忆",
            description_en="Per-step scratch state used by the harness while executing a single loop iteration. Not persisted in V0.",
            description_zh="harness 单次循环步内的临时状态,V0 不持久化。",
            count=0,
            status="scaffolded",
        ),
        MemoryLayer(
            layer="episodic",
            name_en="Episodic memory",
            name_zh="情景记忆",
            description_en="Per-run event log — every AgentEvent emitted by a run is preserved in the run store.",
            description_zh="每次 run 的事件流 — 所有 AgentEvent 都在 run store 里持久化。",
            count=total_events,
            status="live",
        ),
        MemoryLayer(
            layer="semantic",
            name_en="Semantic memory",
            name_zh="语义记忆",
            description_en="Cross-run hypotheses — the agent's tracked claims about reality. Stored in research store.",
            description_zh="跨 run 的假设 — agent 对现实的追踪性论断,放在 research store。",
            count=semantic_count,
            sample=semantic_sample,
            status="live",
        ),
        MemoryLayer(
            layer="procedural",
            name_en="Procedural memory",
            name_zh="过程记忆",
            description_en="Habits / patches the agent has been taught via accepted memory patches. Drives future runs.",
            description_zh="经过接受的 memory patch 累积出的策略 — 影响未来 run 的行为。",
            count=len(accepted_patches),
            sample=[
                {
                    "patch_id": record.patch_id,
                    "decided_at": record.decided_at,
                    "note": record.note,
                }
                for record in accepted_patches[:3]
            ],
            status="live" if accepted_patches else "scaffolded",
        ),
    ]


@router.get("/patches/inbox", response_model=list[PatchSummary])
async def list_patches(status: str = "pending") -> list[PatchSummary]:
    runs = await default_run_store.list()
    decisions = await default_actions_store.list_all()
    summaries: list[PatchSummary] = []
    for run in runs:
        for event in run.events:
            if event.type not in PATCH_TYPES:
                continue
            patch_id = event.event_id
            decision_record = decisions.get(patch_id)
            current_decision: Literal[
                "pending", "accepted", "rejected", "modified"
            ] = decision_record.decision if decision_record else "pending"
            if status != "all" and current_decision != status:
                continue
            summaries.append(
                PatchSummary(
                    patch_id=patch_id,
                    type=event.type,
                    proposal=str(event.data.get("proposal", "")),
                    requires_human_approval=bool(
                        event.data.get("requires_human_approval", False)
                    ),
                    run_id=event.run_id,
                    ts=event.ts,
                    loop_index=int(event.data["loop_index"])
                    if isinstance(event.data.get("loop_index"), int)
                    else None,
                    decision=current_decision,
                    decided_at=decision_record.decided_at if decision_record else None,
                    note=decision_record.note if decision_record else "",
                )
            )
    summaries.sort(key=lambda s: s.ts or 0, reverse=True)
    return summaries


@router.post(
    "/patches/{patch_id}/decide", response_model=PatchSummary
)
async def decide_patch(patch_id: str, payload: PatchDecideRequest) -> PatchSummary:
    runs = await default_run_store.list()
    matching_event = None
    matching_run_id: str | None = None
    for run in runs:
        for event in run.events:
            if event.event_id == patch_id and event.type in PATCH_TYPES:
                matching_event = event
                matching_run_id = run.id
                break
        if matching_event:
            break

    if not matching_event:
        raise HTTPException(status_code=404, detail="patch not found")

    decision_map = {
        "accept": "accepted",
        "reject": "rejected",
        "modify": "modified",
    }
    record = await default_actions_store.set_decision(
        patch_id,
        decision_map[payload.decision],  # type: ignore[arg-type]
        note=payload.note,
    )

    return PatchSummary(
        patch_id=patch_id,
        type=str(matching_event.type),
        proposal=str(matching_event.data.get("proposal", "")),
        requires_human_approval=bool(
            matching_event.data.get("requires_human_approval", False)
        ),
        run_id=matching_run_id,
        ts=matching_event.ts,
        loop_index=int(matching_event.data["loop_index"])
        if isinstance(matching_event.data.get("loop_index"), int)
        else None,
        decision=record.decision,
        decided_at=record.decided_at,
        note=record.note,
    )
