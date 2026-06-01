"""Deterministic V0 critic evaluators.

Each persona produces a :class:`PersonaCritique` based on simple thresholds over
the dossier and its surrounding evidence — no LLM call. This is the bootstrap
implementation that makes the L2 critic loop visible end-to-end. A future V1
swaps these functions for prompted LLM calls (the prompt templates already
live in ``agent/personas/__init__.py``) without changing the harness wiring or
event contract.

Inputs are intentionally small + flat: a dossier-shaped dict (the same payload
the harness emits in ``company_dossier_created``) plus three evidence counters.
The harness is responsible for collecting those from the run's research store
before calling this module.
"""

from __future__ import annotations

from typing import Any

from shinkai_api.agent.personas.runner import PersonaCritique, build_critique


def _coerce_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result < 0.0:
        return 0.0
    if result > 1.0:
        return 1.0
    return result


def evaluate_buffett(dossier: dict[str, Any]) -> PersonaCritique:
    quality = _coerce_float(dossier.get("quality_score"), 0.55)
    ticker = str(dossier.get("ticker") or "candidate")
    if quality >= 0.7:
        return build_critique(
            "buffett",
            verdict="endorse",
            rationale=(
                f"{ticker} clears the quality bar (quality {quality:.2f}); "
                "durable advantage looks plausible given the bottleneck linkage."
            ),
            metadata={"quality_score": quality, "moat_assessment": "narrow"},
        )
    if quality >= 0.5:
        return build_critique(
            "buffett",
            verdict="concerns",
            rationale=(
                f"{ticker} quality is mid-tier ({quality:.2f}); the AI-linked "
                "story may not be improving unit economics yet."
            ),
            metadata={"quality_score": quality, "moat_assessment": "narrow"},
        )
    return build_critique(
        "buffett",
        verdict="reject",
        rationale=(
            f"{ticker} quality score {quality:.2f} is below the floor; "
            "no clear moat, and AI exposure looks incidental."
        ),
        metadata={"quality_score": quality, "moat_assessment": "none"},
    )


def evaluate_short_seller(
    dossier: dict[str, Any],
    *,
    supporting_evidence_count: int,
) -> PersonaCritique:
    underwater = _coerce_float(dossier.get("underwater_score"), 0.55)
    ticker = str(dossier.get("ticker") or "candidate")
    if underwater >= 0.7 and supporting_evidence_count < 2:
        return build_critique(
            "short_seller",
            verdict="reject",
            rationale=(
                f"{ticker} is deeply under-covered ({underwater:.2f}) with only "
                f"{supporting_evidence_count} supporting evidence item(s); "
                "thinly-watched names with weak primary support are textbook "
                "blow-up candidates."
            ),
            metadata={"underwater_score": underwater, "key_short_thesis": "thin_coverage"},
        )
    if underwater >= 0.6:
        return build_critique(
            "short_seller",
            verdict="concerns",
            rationale=(
                f"{ticker} sits where short-sellers like ({underwater:.2f}); "
                "monitor revenue concentration and accounting aggression."
            ),
            metadata={"underwater_score": underwater},
        )
    return build_critique(
        "short_seller",
        verdict="endorse",
        rationale=(
            f"{ticker} has enough analyst coverage ({underwater:.2f}) that "
            "asymmetric downside is unlikely to be hidden."
        ),
        metadata={"underwater_score": underwater},
    )


def evaluate_auditor(
    dossier: dict[str, Any],
    *,
    primary_source_count: int,
    contradicting_evidence_count: int,
) -> PersonaCritique:
    ticker = str(dossier.get("ticker") or "candidate")
    if primary_source_count == 0:
        return build_critique(
            "auditor",
            verdict="reject",
            rationale=(
                f"{ticker} has no primary-source evidence; the agent's claims "
                "rest entirely on secondary or inferred material."
            ),
            metadata={
                "primary_source_count": 0,
                "source_quality_score": 0.2,
            },
        )
    if contradicting_evidence_count > primary_source_count:
        return build_critique(
            "auditor",
            verdict="reject",
            rationale=(
                f"{ticker} has {contradicting_evidence_count} contradicting "
                f"evidence item(s) against only {primary_source_count} primary "
                "supporting source(s); the dossier has not reconciled the conflict."
            ),
            metadata={
                "primary_source_count": primary_source_count,
                "contradicting_evidence_count": contradicting_evidence_count,
                "source_quality_score": 0.35,
            },
        )
    if primary_source_count == 1:
        return build_critique(
            "auditor",
            verdict="concerns",
            rationale=(
                f"{ticker} has a single primary source; thesis depends on one "
                "vantage point and lacks independent confirmation."
            ),
            metadata={
                "primary_source_count": 1,
                "source_quality_score": 0.55,
            },
        )
    return build_critique(
        "auditor",
        verdict="endorse",
        rationale=(
            f"{ticker} is backed by {primary_source_count} primary source(s) "
            "with no unresolved contradictions."
        ),
        metadata={
            "primary_source_count": primary_source_count,
            "source_quality_score": 0.78,
        },
    )


def evaluate_dossier(
    dossier: dict[str, Any],
    *,
    supporting_evidence_count: int,
    contradicting_evidence_count: int,
    primary_source_count: int,
) -> list[PersonaCritique]:
    """Run all three personas against a single dossier."""
    return [
        evaluate_buffett(dossier),
        evaluate_short_seller(
            dossier,
            supporting_evidence_count=supporting_evidence_count,
        ),
        evaluate_auditor(
            dossier,
            primary_source_count=primary_source_count,
            contradicting_evidence_count=contradicting_evidence_count,
        ),
    ]
