"""Agent-level summary endpoint.

Returns the data that powers the ``/agent`` overview page in the frontend —
identity, current status, cross-run "heartrate" counters, and the read-only
capability matrix that describes the triggers / flags the agent currently
supports.

Counters are computed by iterating the run store + research store. For the
current scale (tens of runs, hundreds of events each) this is fast enough; if
the run count grows substantially we will need to precompute these into the
state store.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shinkai_api.core.config import settings
from shinkai_api.research import default_research_store
from shinkai_api.runs import default_run_store

router = APIRouter(prefix="/agent", tags=["agent"])

TERMINAL_STATUSES = {"completed", "failed", "aborted"}
PATCH_TYPES = {
    "memory_patch_proposed",
    "filter_policy_patch_proposed",
    "checklist_patch_proposed",
}


class AgentIdentity(BaseModel):
    name: str = "shinkai"
    chinese_name: str = "深海"
    tagline_en: str = (
        "Long-running, observable, hypothesis-tracking research agent for "
        "under-covered US equities."
    )
    tagline_zh: str = (
        "长跑型、可观察、按假设追踪的投研 agent — 专注水下被低估的美股标的。"
    )
    version: str = "v0"


class AgentStatus(BaseModel):
    status: Literal["idle", "running", "awaiting_checkpoint"]
    active_run_id: str | None = None
    awaiting_run_id: str | None = None
    last_activity_ts: float | None = None
    since_first_activity_ts: float | None = None


class AgentHeartrate(BaseModel):
    total_runs: int = 0
    active_runs: int = 0
    awaiting_checkpoints: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_hypotheses: int = 0
    active_hypotheses: int = 0
    falsified_hypotheses: int = 0
    total_dossiers: int = 0
    total_patches_proposed: int = 0
    total_critic_verdicts: int = 0
    total_critic_rejects: int = 0
    total_injections: int = 0
    total_spirals: int = 0


class AgentTrigger(BaseModel):
    key: str
    name_en: str
    name_zh: str
    default: Any
    description_en: str
    description_zh: str
    options: list[Any] = Field(default_factory=list)


class AgentCapabilities(BaseModel):
    triggers: list[AgentTrigger]


class AgentSummary(BaseModel):
    identity: AgentIdentity
    status: AgentStatus
    heartrate: AgentHeartrate
    capabilities: AgentCapabilities


def _build_triggers() -> list[AgentTrigger]:
    return [
        AgentTrigger(
            key="discovery_mode",
            name_en="Discovery mode",
            name_zh="发现模式",
            default="auto",
            options=["auto", "llm_driven", "deterministic"],
            description_en=(
                "auto: use LLM planner when an API key is configured, else fall "
                "back to the curated supply-chain layers. llm_driven: require "
                "the LLM planner; fail-fast if its output is invalid. "
                "deterministic: never call the LLM."
            ),
            description_zh=(
                "auto:有 API key 时走 LLM,没 key 退到内置供应链层。"
                "llm_driven:必须 LLM,失败就让 run 直接 failed。"
                "deterministic:强制确定性 fallback,不调 LLM。"
            ),
        ),
        AgentTrigger(
            key="allow_live_sources",
            name_en="Live web sources",
            name_zh="实时 web 来源",
            default=False,
            options=[True, False],
            description_en=(
                "Allow the harness to call web_search / web_extract tools. When "
                "false the run uses synthetic evidence — deterministic and free."
            ),
            description_zh=(
                "允许 harness 调 web_search / web_extract。关闭时用合成证据 — "
                "可复现且零成本。"
            ),
        ),
        AgentTrigger(
            key="checkpoints_enabled",
            name_en="Human checkpoints",
            name_zh="人工 checkpoint",
            default=False,
            options=[True, False],
            description_en=(
                "Pause the run before publishing the first dossier and wait for "
                "human approve / reject."
            ),
            description_zh=(
                "在第一个 dossier 发布前让 agent 自己暂停,等用户批准 / 拒绝。"
            ),
        ),
        AgentTrigger(
            key="critics_enabled",
            name_en="L2 critic personas",
            name_zh="L2 评审 persona",
            default=False,
            options=[True, False],
            description_en=(
                "Run Buffett / short-seller / auditor evaluators against every "
                "dossier; aggregated reject penalises hypothesis confidence."
            ),
            description_zh=(
                "对每个 dossier 跑 Buffett / 做空 / 审计 三视角,聚合 reject "
                "自动扣减假设置信度。"
            ),
        ),
        AgentTrigger(
            key="force_llm_planner",
            name_en="Force LLM planner",
            name_zh="强制 LLM 规划",
            default=False,
            options=[True, False],
            description_en=(
                "Equivalent to discovery_mode=llm_driven: refuse to fall back "
                "when planner output is invalid."
            ),
            description_zh=(
                "等同于 discovery_mode=llm_driven:规划输出无效时拒绝 fallback。"
            ),
        ),
    ]


@router.get("/summary", response_model=AgentSummary)
async def get_agent_summary() -> AgentSummary:
    runs = await default_run_store.list()

    active_runs = 0
    awaiting_checkpoints = 0
    completed_runs = 0
    failed_runs = 0
    active_run_id: str | None = None
    awaiting_run_id: str | None = None
    last_ts: float | None = None
    first_ts: float | None = None

    total_dossiers = 0
    total_patches = 0
    total_verdicts = 0
    total_rejects = 0
    total_injections = 0
    total_spirals = 0

    for run in runs:
        if run.status == "awaiting_checkpoint":
            awaiting_checkpoints += 1
            awaiting_run_id = awaiting_run_id or run.id
        if run.status not in TERMINAL_STATUSES:
            active_runs += 1
            if run.status == "running":
                active_run_id = active_run_id or run.id
        if run.status == "completed":
            completed_runs += 1
        if run.status == "failed":
            failed_runs += 1

        for event in run.events:
            ts = event.ts
            if ts:
                if last_ts is None or ts > last_ts:
                    last_ts = ts
                if first_ts is None or ts < first_ts:
                    first_ts = ts
            if event.type == "company_dossier_created":
                total_dossiers += 1
            elif event.type in PATCH_TYPES:
                total_patches += 1
            elif event.type == "critic_aggregated":
                total_verdicts += 1
                if event.data.get("final") == "reject":
                    total_rejects += 1
            elif event.type == "human_injection":
                total_injections += 1
            elif event.type == "child_run_created":
                total_spirals += 1

    total_hypotheses = 0
    active_hypotheses = 0
    falsified_hypotheses = 0
    for run in runs:
        hypotheses = await default_research_store.get_hypotheses_by_run(run.id)
        for hypothesis in hypotheses:
            total_hypotheses += 1
            if hypothesis.state == "active":
                active_hypotheses += 1
            elif hypothesis.state == "falsified":
                falsified_hypotheses += 1

    if awaiting_checkpoints > 0:
        status: Literal["idle", "running", "awaiting_checkpoint"] = "awaiting_checkpoint"
    elif active_runs > 0:
        status = "running"
    else:
        status = "idle"

    return AgentSummary(
        identity=AgentIdentity(),
        status=AgentStatus(
            status=status,
            active_run_id=active_run_id,
            awaiting_run_id=awaiting_run_id,
            last_activity_ts=last_ts,
            since_first_activity_ts=first_ts,
        ),
        heartrate=AgentHeartrate(
            total_runs=len(runs),
            active_runs=active_runs,
            awaiting_checkpoints=awaiting_checkpoints,
            completed_runs=completed_runs,
            failed_runs=failed_runs,
            total_hypotheses=total_hypotheses,
            active_hypotheses=active_hypotheses,
            falsified_hypotheses=falsified_hypotheses,
            total_dossiers=total_dossiers,
            total_patches_proposed=total_patches,
            total_critic_verdicts=total_verdicts,
            total_critic_rejects=total_rejects,
            total_injections=total_injections,
            total_spirals=total_spirals,
        ),
        capabilities=AgentCapabilities(triggers=_build_triggers()),
    )


# settings is imported for future use (e.g. exposing real configured defaults
# rather than the hardcoded matrix). Keep the import explicit so a future
# refactor can wire it in without re-adding it.
_ = settings
