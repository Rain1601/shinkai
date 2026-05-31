from __future__ import annotations

from shinkai_api.eval.ground_truth import (
    GROUND_TRUTH_CASES,
    expected_verdict_for,
    score_against_ground_truth,
)


def test_ground_truth_cases_cover_both_classes() -> None:
    verdicts = {case.expected_verdict for case in GROUND_TRUTH_CASES}
    assert "underwater_high_quality" in verdicts
    assert "covered_or_mainstream" in verdicts


def test_perfect_agent_scores_precision_and_recall_one() -> None:
    picks = {case.ticker.upper(): case.expected_verdict for case in GROUND_TRUTH_CASES}

    result = score_against_ground_truth(picks)

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["mismatches"] == []


def test_false_positive_detected_when_mainstream_flagged_underwater() -> None:
    picks = {
        "NVDA": "underwater_high_quality",
        "POWL": "underwater_high_quality",
        "FORM": "underwater_high_quality",
        "ONTO": "underwater_high_quality",
    }

    result = score_against_ground_truth(picks)

    assert result["false_positives"] >= 1
    assert any(mismatch["ticker"] == "NVDA" for mismatch in result["mismatches"])
    assert result["precision"] < 1.0


def test_false_negative_detected_when_underwater_missed() -> None:
    picks = {
        "NVDA": "covered_or_mainstream",
        "ASML": "covered_or_mainstream",
        "TSM": "covered_or_mainstream",
        # POWL, FORM, ONTO missing — they should be in the underwater bucket
    }

    result = score_against_ground_truth(picks)

    assert result["false_negatives"] >= 3
    assert result["recall"] == 0.0


def test_expected_verdict_lookup() -> None:
    assert expected_verdict_for("NVDA") == "covered_or_mainstream"
    assert expected_verdict_for("POWL") == "underwater_high_quality"
    assert expected_verdict_for("UNKNOWN_TICKER") is None
