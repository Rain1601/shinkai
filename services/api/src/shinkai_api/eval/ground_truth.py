"""Hand-curated ground-truth labels for evaluation.

L1 of the 4-layer eval framework (alignment-v2 §9). These cases are deliberately small
and hand-labeled: the goal is to detect regressions where the agent's classification
diverges from the expected verdict, not to score generative quality.

To add a case: encode a triplet of (ticker, layer, expected_verdict) where
expected_verdict ∈ {"underwater_high_quality", "covered_or_mainstream", "low_quality"}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GroundTruthVerdict = Literal[
    "underwater_high_quality",
    "covered_or_mainstream",
    "low_quality",
]


@dataclass(frozen=True)
class GroundTruthCase:
    ticker: str
    company_name: str
    supply_chain_layer: str
    expected_verdict: GroundTruthVerdict
    notes: str = ""


GROUND_TRUTH_CASES: list[GroundTruthCase] = [
    GroundTruthCase(
        ticker="NVDA",
        company_name="NVIDIA",
        supply_chain_layer="AI accelerators",
        expected_verdict="covered_or_mainstream",
        notes="Mega-cap, headline tracked by uteki; shinkai must NOT flag as underwater.",
    ),
    GroundTruthCase(
        ticker="ASML",
        company_name="ASML",
        supply_chain_layer="EUV lithography",
        expected_verdict="covered_or_mainstream",
        notes="Headline supplier; must not be classified as underwater.",
    ),
    GroundTruthCase(
        ticker="TSM",
        company_name="TSMC",
        supply_chain_layer="Foundry",
        expected_verdict="covered_or_mainstream",
        notes="Headline foundry; must not be classified as underwater.",
    ),
    GroundTruthCase(
        ticker="POWL",
        company_name="Powell Industries",
        supply_chain_layer="Power and electrical infrastructure",
        expected_verdict="underwater_high_quality",
        notes=(
            "Second-order beneficiary of AI data-center power buildout; "
            "legitimate underwater pick."
        ),
    ),
    GroundTruthCase(
        ticker="FORM",
        company_name="FormFactor",
        supply_chain_layer="Advanced packaging, HBM, and test capacity",
        expected_verdict="underwater_high_quality",
        notes="Probe-card supplier exposed to HBM/advanced-packaging ramp.",
    ),
    GroundTruthCase(
        ticker="ONTO",
        company_name="Onto Innovation",
        supply_chain_layer="Advanced packaging, HBM, and test capacity",
        expected_verdict="underwater_high_quality",
        notes="Metrology/inspection supplier; modest follower coverage relative to ASML peers.",
    ),
]


def expected_verdict_for(ticker: str) -> GroundTruthVerdict | None:
    for case in GROUND_TRUTH_CASES:
        if case.ticker.upper() == ticker.upper():
            return case.expected_verdict
    return None


def score_against_ground_truth(
    agent_picks_by_ticker: dict[str, str],
) -> dict[str, float | int | list[dict[str, str]]]:
    """Compare agent's per-ticker decision against ground truth.

    `agent_picks_by_ticker` maps ticker -> agent's verdict
    (one of: "underwater_high_quality", "covered_or_mainstream", "low_quality").
    Returns precision, recall, and the list of mismatches for debugging.
    """
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    mismatches: list[dict[str, str]] = []
    for case in GROUND_TRUTH_CASES:
        expected = case.expected_verdict
        actual = agent_picks_by_ticker.get(case.ticker.upper())
        if actual is None:
            if expected == "underwater_high_quality":
                false_negatives += 1
                mismatches.append(
                    {
                        "ticker": case.ticker,
                        "expected": expected,
                        "actual": "missing",
                    }
                )
            else:
                true_negatives += 1
            continue
        if actual == expected:
            if expected == "underwater_high_quality":
                true_positives += 1
            else:
                true_negatives += 1
        else:
            if expected == "underwater_high_quality":
                false_negatives += 1
            elif actual == "underwater_high_quality":
                false_positives += 1
            mismatches.append(
                {
                    "ticker": case.ticker,
                    "expected": expected,
                    "actual": actual,
                }
            )
    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "mismatches": mismatches,
    }
