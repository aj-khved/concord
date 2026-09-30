"""Shared business logic for the review workflow, used by BOTH the
server-rendered HTML routes (app.py) and the JSON REST API (rest.py). Kept
here, not duplicated across the two, since "what does this pair's status
resolve to" and "what happens when a human decides a pair" must behave
identically regardless of which interface is used to reach it."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from concord.db.models import HumanReview, LlmAdjudication, MatchCandidate
from concord.golden.rebuild import rebuild_golden_vendors
from concord.matching.pair_key import pair_key
from concord.review.resolution import PairStatus, resolve_pair


def latest_batch_id(session: Session) -> uuid.UUID | None:
    """match_candidates is append-only: every matching-engine run adds a new
    batch rather than replacing the last one. Only the most recent batch
    reflects current, authoritative pair resolutions — older batches are
    audit history, not something to merge counts across."""
    return session.execute(
        select(MatchCandidate.batch_id).order_by(MatchCandidate.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def adjudications_by_pair(session: Session) -> dict[tuple[str, str], LlmAdjudication]:
    return {
        pair_key(a.record_id_1, a.record_id_2): a
        for a in session.execute(select(LlmAdjudication)).scalars().all()
    }


def reviews_by_pair(session: Session) -> dict[tuple[str, str], HumanReview]:
    return {
        pair_key(r.record_id_1, r.record_id_2): r
        for r in session.execute(select(HumanReview)).scalars().all()
    }


def resolved_statuses(session: Session) -> dict[uuid.UUID, PairStatus]:
    batch_id = latest_batch_id(session)
    candidates = (
        session.execute(select(MatchCandidate).where(MatchCandidate.batch_id == batch_id))
        .scalars()
        .all()
        if batch_id
        else []
    )
    adjudications = adjudications_by_pair(session)
    reviews = reviews_by_pair(session)
    return {
        c.id: resolve_pair(
            c,
            adjudications.get(pair_key(c.record_id_1, c.record_id_2)),
            reviews.get(pair_key(c.record_id_1, c.record_id_2)),
        )
        for c in candidates
    }


class CandidateNotFoundError(Exception):
    pass


class InvalidDecisionError(Exception):
    pass


@dataclass
class DecisionOutcome:
    already_reviewed: bool


def decide_pair(
    session: Session, candidate_id: uuid.UUID, decision: str, reviewer: str, note: str | None
) -> DecisionOutcome:
    if decision not in ("approve", "reject"):
        raise InvalidDecisionError("decision must be 'approve' or 'reject'")

    candidate = session.get(MatchCandidate, candidate_id)
    if candidate is None:
        raise CandidateNotFoundError(f"Match candidate {candidate_id} not found")

    id_1, id_2 = (uuid.UUID(k) for k in pair_key(candidate.record_id_1, candidate.record_id_2))
    already_reviewed = session.execute(
        select(HumanReview).where(HumanReview.record_id_1 == id_1, HumanReview.record_id_2 == id_2)
    ).scalar_one_or_none()

    if already_reviewed is not None:
        return DecisionOutcome(already_reviewed=True)

    session.add(
        HumanReview(
            record_id_1=id_1, record_id_2=id_2, decision=decision, reviewer=reviewer, note=note
        )
    )
    session.commit()
    rebuild_golden_vendors(session)
    return DecisionOutcome(already_reviewed=False)
