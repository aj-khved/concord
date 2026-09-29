"""Resolves a match_candidate's final status by combining the deterministic
engine (M3), LLM adjudication (M4), and any human decision (M5) — one
function, so there's exactly one place that decides "is this pair a match,"
rather than that logic being duplicated across the UI, the golden-record
builder, and reporting scripts.

Precedence: a human decision is always final and overrides everything else,
since a person looking at the actual evidence is the highest-trust signal in
the system. Absent that, the LLM's adjudication (if confident) resolves a
pending_review pair. Absent both, the pair still needs a human."""

from enum import StrEnum
from typing import Protocol


class PairStatus(StrEnum):
    MATCH = "match"
    NON_MATCH = "non_match"
    NEEDS_REVIEW = "needs_review"


class _MatchCandidateLike(Protocol):
    tier: str


class _LlmAdjudicationLike(Protocol):
    outcome: str


class _HumanReviewLike(Protocol):
    decision: str  # "approve" or "reject"


def resolve_pair(
    candidate: _MatchCandidateLike,
    llm_adjudication: _LlmAdjudicationLike | None,
    human_review: _HumanReviewLike | None,
) -> PairStatus:
    if human_review is not None:
        return PairStatus.MATCH if human_review.decision == "approve" else PairStatus.NON_MATCH

    if candidate.tier == "auto_merge":
        return PairStatus.MATCH
    if candidate.tier == "auto_reject":
        return PairStatus.NON_MATCH

    # tier == "pending_review"
    if llm_adjudication is not None:
        if llm_adjudication.outcome == "confirmed_match":
            return PairStatus.MATCH
        if llm_adjudication.outcome == "confirmed_non_match":
            return PairStatus.NON_MATCH
        # outcome == "uncertain" falls through to needing a human

    return PairStatus.NEEDS_REVIEW
