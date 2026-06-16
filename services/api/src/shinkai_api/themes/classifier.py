"""LLM-driven theme classifier.

Takes the set of currently-known research themes (title, anchor, sample
hypotheses) and asks DeepSeek to group them into 2-6 coherent clusters and
infer the *logical* edges between themes (A is a prerequisite of B, A is
adjacent to B, B is downstream of A).

Falls back to a single ``unclassified`` cluster when no key is configured or
when the LLM output fails validation — same defensive pattern the planner
uses, so tests stay deterministic without a key.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable

from pydantic import BaseModel, ValidationError

from shinkai_api.core.config import settings
from shinkai_api.llm import DeepSeekClient, DeepSeekError
from shinkai_api.themes.models import (
    ThemeCluster,
    ThemeEdge,
    ThemeGraph,
    empty_graph,
)

logger = logging.getLogger(__name__)


MAX_THEMES_FOR_LLM = 40
MAX_TITLE_LEN = 120
MAX_HYP_SUMMARY_LEN = 240


class ThemeInfo(BaseModel):
    theme_id: str
    title: str
    anchor: str = ""
    hypothesis_summary: str = ""


SYSTEM_PROMPT = (
    "You are shinkai's knowledge-graph classifier for investment research themes. "
    "Given a list of themes, do TWO things: "
    "(1) cluster them into 2–6 coherent groups by domain (e.g. 'AI infrastructure', "
    "'energy & power', 'semiconductors', 'biotech') with a short Chinese-friendly "
    "name and a one-line rationale. "
    "(2) infer the *logical* edges between themes — A is a prerequisite of B, A is "
    "adjacent to B, B is downstream of A — only when the connection is non-trivial. "
    "Return strict JSON only, no commentary."
)


def _user_prompt(themes: list[ThemeInfo]) -> str:
    listing = [
        {
            "theme_id": t.theme_id,
            "title": t.title[:MAX_TITLE_LEN],
            "anchor": t.anchor[:MAX_TITLE_LEN],
            "hypotheses": t.hypothesis_summary[:MAX_HYP_SUMMARY_LEN],
        }
        for t in themes
    ]
    return (
        "Themes to classify:\n"
        + json.dumps(listing, ensure_ascii=False, indent=2)
        + "\n\nReturn JSON with this exact shape:\n"
        + json.dumps(
            {
                "clusters": [
                    {
                        "cluster_id": "stable-slug-like-ai-infrastructure",
                        "cluster_name": "AI 基础设施",
                        "rationale": "one-line reason these themes belong together",
                        "theme_ids": ["theme_id_1", "theme_id_2"],
                    }
                ],
                "edges": [
                    {
                        "from_theme_id": "theme_id_1",
                        "to_theme_id": "theme_id_2",
                        "kind": "prerequisite | adjacent | downstream",
                        "weight": 0.0,
                        "reason": "one-line why these are logically linked",
                    }
                ],
                "unclustered_theme_ids": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n\nRules:\n"
        + "- Every theme_id in the input must appear in EXACTLY one cluster's theme_ids "
        + "OR in unclustered_theme_ids.\n"
        + "- Use 2-6 clusters; do not put every theme in its own cluster.\n"
        + "- Only include edges with kind in {prerequisite, adjacent, downstream}; "
        + "skip weak/uncertain links.\n"
        + "- weight ∈ [0.0, 1.0] — higher = more confident.\n"
        + "- cluster_id must be a stable lowercased slug.\n"
    )


def _slug(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return slug or "cluster"


def _deterministic_fallback(
    themes: list[ThemeInfo], *, generator: str = "deterministic_fallback",
    reject_reason: str | None = None,
) -> ThemeGraph:
    """One bucket holding every theme — keeps the UI shape intact when the LLM
    is unavailable or rejected."""
    return ThemeGraph(
        generated_at=time.time(),
        generator=generator,  # type: ignore[arg-type]
        clusters=[
            ThemeCluster(
                cluster_id="unclassified",
                cluster_name="未分类",
                rationale="LLM 不可用,所有主题暂归一处",
                theme_ids=[t.theme_id for t in themes],
            )
        ]
        if themes
        else [],
        edges=[],
        unclustered_theme_ids=[],
        reject_reason=reject_reason,
    )


def _validate_llm_output(
    payload: dict, theme_ids: set[str]
) -> tuple[list[ThemeCluster], list[ThemeEdge], list[str], str | None]:
    """Parse + validate LLM JSON. Returns (clusters, edges, unclustered, reject_reason).
    If reject_reason is non-None the caller should fall back."""

    raw_clusters = payload.get("clusters")
    raw_edges = payload.get("edges", [])
    raw_unclustered = payload.get("unclustered_theme_ids", [])

    if not isinstance(raw_clusters, list) or not raw_clusters:
        return [], [], [], "missing clusters"

    seen_theme_ids: set[str] = set()
    clusters: list[ThemeCluster] = []
    for item in raw_clusters:
        if not isinstance(item, dict):
            continue
        cluster_id = _slug(str(item.get("cluster_id") or item.get("cluster_name") or ""))
        cluster_name = str(item.get("cluster_name") or "").strip()
        if not cluster_id or not cluster_name:
            continue
        member_ids = item.get("theme_ids") or []
        if not isinstance(member_ids, list):
            continue
        members: list[str] = []
        for tid in member_ids:
            sid = str(tid).strip()
            if sid in theme_ids and sid not in seen_theme_ids:
                members.append(sid)
                seen_theme_ids.add(sid)
        if not members:
            continue
        clusters.append(
            ThemeCluster(
                cluster_id=cluster_id,
                cluster_name=cluster_name,
                rationale=str(item.get("rationale") or "").strip()[:300],
                theme_ids=members,
            )
        )

    if not clusters:
        return [], [], [], "no valid clusters after validation"

    edges: list[ThemeEdge] = []
    for item in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(item, dict):
            continue
        a = str(item.get("from_theme_id") or "").strip()
        b = str(item.get("to_theme_id") or "").strip()
        if a not in theme_ids or b not in theme_ids or a == b:
            continue
        kind = str(item.get("kind") or "adjacent").strip()
        if kind not in {"prerequisite", "adjacent", "downstream", "shares_entity"}:
            kind = "adjacent"
        try:
            weight = float(item.get("weight", 0.5))
        except (TypeError, ValueError):
            weight = 0.5
        weight = max(0.0, min(1.0, weight))
        edges.append(
            ThemeEdge(
                from_theme_id=a,
                to_theme_id=b,
                kind=kind,  # type: ignore[arg-type]
                weight=weight,
                reason=str(item.get("reason") or "").strip()[:240],
            )
        )

    unclustered: list[str] = []
    for tid in raw_unclustered if isinstance(raw_unclustered, list) else []:
        sid = str(tid).strip()
        if sid in theme_ids and sid not in seen_theme_ids:
            unclustered.append(sid)
            seen_theme_ids.add(sid)

    # Any theme not placed anywhere drops into unclustered so the UI doesn't
    # silently lose it.
    for tid in theme_ids:
        if tid not in seen_theme_ids:
            unclustered.append(tid)

    return clusters, edges, unclustered, None


async def classify_themes(themes: Iterable[ThemeInfo]) -> ThemeGraph:
    """Classify the given themes into clusters + edges via DeepSeek.

    Falls back to a single ``unclassified`` cluster when no key is configured,
    the API errors, or the response fails validation.
    """
    theme_list = list(themes)
    if not theme_list:
        return empty_graph()

    if len(theme_list) > MAX_THEMES_FOR_LLM:
        # Keep the prompt bounded — newest first.
        theme_list = theme_list[:MAX_THEMES_FOR_LLM]

    if not settings.deepseek_api_key:
        return _deterministic_fallback(theme_list, reject_reason="no_api_key")

    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.llm_model,
    )

    try:
        raw = await client.chat_json(
            system=SYSTEM_PROMPT,
            user=_user_prompt(theme_list),
            temperature=0.2,
            max_tokens=2400,
        )
    except DeepSeekError as exc:
        logger.warning("theme classifier: deepseek error %s", exc)
        return _deterministic_fallback(theme_list, reject_reason=f"deepseek_error: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("theme classifier: unexpected error %s", exc)
        return _deterministic_fallback(theme_list, reject_reason=f"unexpected: {exc}")

    theme_id_set = {t.theme_id for t in theme_list}
    try:
        clusters, edges, unclustered, reject_reason = _validate_llm_output(raw, theme_id_set)
    except ValidationError as exc:
        logger.warning("theme classifier: validation error %s", exc)
        return _deterministic_fallback(
            theme_list, reject_reason=f"validation_error: {exc}"
        )

    if reject_reason:
        logger.warning("theme classifier: reject %s", reject_reason)
        return _deterministic_fallback(
            theme_list,
            generator="fallback_after_reject",
            reject_reason=reject_reason,
        )

    return ThemeGraph(
        generated_at=time.time(),
        generator="deepseek_llm",
        clusters=clusters,
        edges=edges,
        unclustered_theme_ids=unclustered,
        reject_reason=None,
    )
