"""JSON REST API (FR10): list/search vendors, vendor detail, list pending
reviews, submit a review decision, trigger a pipeline run.

Reuses concord.api.review_service for all business logic shared with the
HTML routes in app.py — this router only handles request/response shaping.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from concord.api.review_service import (
    CandidateNotFoundError,
    InvalidDecisionError,
    adjudications_by_pair,
    decide_pair,
    latest_batch_id,
    resolved_statuses,
)
from concord.api.schemas import (
    IngestionTriggerResponse,
    PendingReviewItemOut,
    PipelineRunOut,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    VendorDetailOut,
    VendorListOut,
    VendorSummary,
)
from concord.db.models import (
    GoldenVendor,
    MatchCandidate,
    NormalizedVendorRecord,
    PipelineRun,
    VendorRiskProfile,
)
from concord.db.session import get_session
from concord.matching.pair_key import pair_key
from concord.observability.pipeline_run import track_pipeline_run
from concord.pipeline import run_ingestion
from concord.review.resolution import PairStatus

router = APIRouter()


@router.get("/vendors", response_model=VendorListOut)
def list_vendors(
    search: str | None = Query(None, description="Case-insensitive substring match on legal_name"),
    risk_level: str | None = Query(None, description="Filter to an exact risk_level"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    query = select(GoldenVendor)
    if search:
        query = query.where(GoldenVendor.legal_name.ilike(f"%{search}%"))
    all_matching = session.execute(query.order_by(GoldenVendor.member_count.desc())).scalars().all()

    risk_by_tax_id = {
        p.tax_id: p for p in session.execute(select(VendorRiskProfile)).scalars().all()
    }

    if risk_level:
        all_matching = [
            v
            for v in all_matching
            if risk_by_tax_id.get(v.tax_id, None)
            and risk_by_tax_id[v.tax_id].risk_level == risk_level
        ]

    page = all_matching[offset : offset + limit]
    items = [
        VendorSummary(
            id=v.id,
            legal_name=v.legal_name,
            city=v.city,
            category=v.category,
            member_count=v.member_count,
            risk_level=risk_by_tax_id[v.tax_id].risk_level if v.tax_id in risk_by_tax_id else None,
        )
        for v in page
    ]
    return VendorListOut(total=len(all_matching), items=items)


@router.get("/vendors/{vendor_id}", response_model=VendorDetailOut)
def get_vendor(vendor_id: str, session: Session = Depends(get_session)):
    try:
        parsed_id = uuid.UUID(vendor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid vendor id") from exc

    vendor = session.get(GoldenVendor, parsed_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    members = (
        session.execute(
            select(NormalizedVendorRecord).where(
                NormalizedVendorRecord.golden_vendor_id == vendor.id
            )
        )
        .scalars()
        .all()
    )
    risk_profile = (
        session.execute(
            select(VendorRiskProfile).where(VendorRiskProfile.tax_id == vendor.tax_id)
        ).scalar_one_or_none()
        if vendor.tax_id
        else None
    )

    return VendorDetailOut(
        id=vendor.id,
        legal_name=vendor.legal_name,
        address_line1=vendor.address_line1,
        city=vendor.city,
        state=vendor.state,
        postal_code=vendor.postal_code,
        country=vendor.country,
        tax_id=vendor.tax_id,
        phone=vendor.phone,
        category=vendor.category,
        member_count=vendor.member_count,
        risk_profile=risk_profile,
        members=members,
    )


@router.get("/review", response_model=list[PendingReviewItemOut])
def list_pending_review(session: Session = Depends(get_session)):
    statuses = resolved_statuses(session)
    batch_id = latest_batch_id(session)
    candidates_by_id = {
        c.id: c
        for c in session.execute(select(MatchCandidate).where(MatchCandidate.batch_id == batch_id))
        .scalars()
        .all()
    }
    adjudications = adjudications_by_pair(session)
    records_by_id = {
        r.id: r for r in session.execute(select(NormalizedVendorRecord)).scalars().all()
    }

    items = []
    for cid, status in statuses.items():
        if status != PairStatus.NEEDS_REVIEW:
            continue
        candidate = candidates_by_id[cid]
        adjudication = adjudications.get(pair_key(candidate.record_id_1, candidate.record_id_2))
        items.append(
            PendingReviewItemOut(
                match_candidate_id=cid,
                score=candidate.score,
                record_a=records_by_id[candidate.record_id_1],
                record_b=records_by_id[candidate.record_id_2],
                llm_outcome=adjudication.outcome if adjudication else None,
                llm_confidence=adjudication.confidence if adjudication else None,
                llm_rationale=adjudication.rationale if adjudication else None,
            )
        )
    return items


@router.post("/review/{candidate_id}/decide", response_model=ReviewDecisionResponse)
def submit_review_decision(
    candidate_id: str,
    body: ReviewDecisionRequest,
    session: Session = Depends(get_session),
):
    try:
        parsed_id = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid candidate id") from exc

    try:
        outcome = decide_pair(session, parsed_id, body.decision, body.reviewer, body.note)
    except InvalidDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ReviewDecisionResponse(
        match_candidate_id=parsed_id,
        decision=body.decision,
        already_reviewed=outcome.already_reviewed,
    )


@router.post("/pipeline/ingestion", response_model=IngestionTriggerResponse)
def trigger_ingestion(session: Session = Depends(get_session)):
    """Triggers the M2 ingestion pipeline synchronously. Deliberately the
    only pipeline stage exposed for on-demand triggering via API: it's
    idempotent (upserts) and fast at this data volume. Matching/LLM
    adjudication cost real money and take longer, so they stay
    script-triggered rather than a click away in an API a stranger could
    call — a task queue would be the right answer at real scale, not this."""
    with track_pipeline_run(session, "ingestion") as run:
        summary = run_ingestion(Path("data/synthetic"), session)
        run.summary = {"batch_id": str(summary.batch_id), "per_source": summary.per_source}

    return IngestionTriggerResponse(batch_id=summary.batch_id, per_source=summary.per_source)


@router.get("/pipeline-runs", response_model=list[PipelineRunOut])
def list_pipeline_runs(
    limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
):
    runs = (
        session.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return runs
