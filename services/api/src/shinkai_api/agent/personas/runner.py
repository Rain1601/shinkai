"""Run the three critic personas against a dossier and aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CriticVerdict = Literal["endorse", "concerns", "reject"]


@dataclass
class PersonaCritique:
    persona: str
    verdict: CriticVerdict
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)


def build_critique(
    persona: str,
    *,
    verdict: CriticVerdict,
    rationale: str,
    metadata: dict[str, Any] | None = None,
) -> PersonaCritique:
    return PersonaCritique(
        persona=persona,
        verdict=verdict,
        rationale=rationale,
        metadata=metadata or {},
    )


def aggregate_critiques(critiques: list[PersonaCritique]) -> dict[str, Any]:
    """Reduce 3 persona verdicts to a single decision recommendation.

    Conservative rule per alignment-v2: any 'reject' is reject; otherwise majority.
    Used when the harness needs a single critic signal but persona detail is
    preserved for audit.
    """
    if not critiques:
        return {"final": "concerns", "vote_summary": {}, "critiques": []}
    votes = [critique.verdict for critique in critiques]
    if "reject" in votes:
        final: CriticVerdict = "reject"
    elif votes.count("endorse") > len(votes) // 2:
        final = "endorse"
    else:
        final = "concerns"
    summary = {
        "endorse": votes.count("endorse"),
        "concerns": votes.count("concerns"),
        "reject": votes.count("reject"),
    }
    return {
        "final": final,
        "vote_summary": summary,
        "critiques": [
            {
                "persona": critique.persona,
                "verdict": critique.verdict,
                "rationale": critique.rationale,
            }
            for critique in critiques
        ],
    }
