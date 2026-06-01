"""Hypothesis update helpers.

The :class:`Hypothesis` and :class:`ConfidencePoint` models live in
:mod:`shinkai_api.research.models` so the research store can persist them
without pulling the agent harness into its import chain. This module owns the
business rules: how a piece of evidence (or a human correction) translates into
a confidence delta.

The V0 algorithm — :data:`CONFIDENCE_METHOD` — is an evidence-weighted average
that shifts confidence proportionally to source reliability. A ``method`` field
is stored on every update so a future swap to a Bayesian update is
non-breaking for downstream consumers (they read whatever ``method`` the event
declares).
"""

from __future__ import annotations

from shinkai_api.research.models import (
    ConfidenceChangeKind,
    ConfidencePoint,
    Hypothesis,
)

CONFIDENCE_METHOD = "evidence_weighted_average_v0"
# Maximum delta a single piece of evidence can apply to confidence. The actual
# delta is ``reliability_score * MAX_EVIDENCE_DELTA``.
MAX_EVIDENCE_DELTA = 0.15
HUMAN_CORRECTION_DELTA = 0.15


def update_confidence(
    prev_confidence: float,
    *,
    reliability_score: float,
    kind: ConfidenceChangeKind,
) -> tuple[float, float, str]:
    """Return (new_confidence, delta, method) for an evidence-weighted update."""
    if kind == "human_correction":
        delta = -HUMAN_CORRECTION_DELTA
    else:
        weight = max(0.0, min(1.0, reliability_score)) * MAX_EVIDENCE_DELTA
        delta = weight if kind == "support" else -weight
    new_confidence = max(0.0, min(1.0, prev_confidence + delta))
    return new_confidence, round(new_confidence - prev_confidence, 4), CONFIDENCE_METHOD


def promote_supporting(
    hypothesis: Hypothesis,
    *,
    evidence_id: str,
    reliability_score: float,
) -> ConfidencePoint:
    new_conf, delta, method = update_confidence(
        hypothesis.confidence,
        reliability_score=reliability_score,
        kind="support",
    )
    hypothesis.confidence = new_conf
    if evidence_id not in hypothesis.supporting_evidence_ids:
        hypothesis.supporting_evidence_ids.append(evidence_id)
    point = ConfidencePoint(
        confidence=new_conf,
        delta=delta,
        evidence_id=evidence_id,
        kind="support",
        method=method,
    )
    hypothesis.confidence_history.append(point)
    return point


def promote_contradicting(
    hypothesis: Hypothesis,
    *,
    evidence_id: str,
    reliability_score: float,
) -> ConfidencePoint:
    new_conf, delta, method = update_confidence(
        hypothesis.confidence,
        reliability_score=reliability_score,
        kind="contradict",
    )
    hypothesis.confidence = new_conf
    if evidence_id not in hypothesis.contradicting_evidence_ids:
        hypothesis.contradicting_evidence_ids.append(evidence_id)
    point = ConfidencePoint(
        confidence=new_conf,
        delta=delta,
        evidence_id=evidence_id,
        kind="contradict",
        method=method,
    )
    hypothesis.confidence_history.append(point)
    return point


CRITIC_PENALTY_DELTA = 0.08


def apply_critic_penalty(
    hypothesis: Hypothesis,
    *,
    dossier_id: str,
) -> ConfidencePoint:
    """Apply a critic-aggregated reject penalty to confidence.

    Smaller than a human correction since critics are V0 deterministic rules,
    not yet calibrated LLM evaluators. The delta is recorded with method
    ``critic_aggregated_v0`` so a future LLM-backed critic can be distinguished
    in the trajectory.
    """
    prev = hypothesis.confidence
    new_conf = max(0.0, min(1.0, prev - CRITIC_PENALTY_DELTA))
    delta = round(new_conf - prev, 4)
    hypothesis.confidence = new_conf
    point = ConfidencePoint(
        confidence=new_conf,
        delta=delta,
        evidence_id=f"critic_{dossier_id}",
        kind="contradict",
        method="critic_aggregated_v0",
    )
    hypothesis.confidence_history.append(point)
    return point


def apply_human_correction(
    hypothesis: Hypothesis,
    *,
    injection_id: str,
) -> ConfidencePoint:
    new_conf, delta, method = update_confidence(
        hypothesis.confidence,
        reliability_score=1.0,
        kind="human_correction",
    )
    hypothesis.confidence = new_conf
    point = ConfidencePoint(
        confidence=new_conf,
        delta=delta,
        evidence_id=f"inject_{injection_id}",
        kind="human_correction",
        method=method,
    )
    hypothesis.confidence_history.append(point)
    return point


def mark_falsified(hypothesis: Hypothesis, *, reason: str) -> None:
    prev = hypothesis.confidence
    hypothesis.state = "falsified"
    hypothesis.confidence = 0.0
    hypothesis.confidence_history.append(
        ConfidencePoint(
            confidence=0.0,
            delta=round(0.0 - prev, 4),
            evidence_id="falsification",
            kind="contradict",
            method="manual_falsification",
        )
    )
    hypothesis.falsification_condition = (
        hypothesis.falsification_condition + f" | FALSIFIED: {reason}"
    ).strip(" |")


def supersede(hypothesis: Hypothesis, *, replaced_by_id: str) -> None:
    hypothesis.state = "superseded"
    hypothesis.superseded_by_id = replaced_by_id
