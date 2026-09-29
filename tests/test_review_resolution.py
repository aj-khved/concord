from dataclasses import dataclass

from concord.review.resolution import PairStatus, resolve_pair


@dataclass
class _Candidate:
    tier: str


@dataclass
class _Adjudication:
    outcome: str


@dataclass
class _Review:
    decision: str


def test_auto_merge_is_match_with_no_llm_or_human():
    assert resolve_pair(_Candidate("auto_merge"), None, None) == PairStatus.MATCH


def test_auto_reject_is_non_match_with_no_llm_or_human():
    assert resolve_pair(_Candidate("auto_reject"), None, None) == PairStatus.NON_MATCH


def test_pending_review_with_no_adjudication_needs_review():
    assert resolve_pair(_Candidate("pending_review"), None, None) == PairStatus.NEEDS_REVIEW


def test_pending_review_confirmed_match():
    result = resolve_pair(_Candidate("pending_review"), _Adjudication("confirmed_match"), None)
    assert result == PairStatus.MATCH


def test_pending_review_confirmed_non_match():
    result = resolve_pair(_Candidate("pending_review"), _Adjudication("confirmed_non_match"), None)
    assert result == PairStatus.NON_MATCH


def test_pending_review_uncertain_still_needs_review():
    result = resolve_pair(_Candidate("pending_review"), _Adjudication("uncertain"), None)
    assert result == PairStatus.NEEDS_REVIEW


def test_human_approval_overrides_auto_reject():
    result = resolve_pair(_Candidate("auto_reject"), None, _Review("approve"))
    assert result == PairStatus.MATCH


def test_human_rejection_overrides_llm_confirmed_match():
    result = resolve_pair(
        _Candidate("pending_review"), _Adjudication("confirmed_match"), _Review("reject")
    )
    assert result == PairStatus.NON_MATCH
