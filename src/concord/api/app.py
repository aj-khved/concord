"""Minimal server-rendered review UI (M5). Deliberately not a React SPA —
see docs/charter.md §9.6 for why: proving the review workflow matters more
right now than frontend polish. A REST API (FR10) comes in M7."""

import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from concord.db.models import (
    GoldenVendor,
    HumanReview,
    LlmAdjudication,
    MatchCandidate,
    NormalizedVendorRecord,
)
from concord.db.session import get_session
from concord.golden.rebuild import rebuild_golden_vendors
from concord.review.resolution import PairStatus, resolve_pair

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Concord")


def _session() -> Session:
    return next(get_session())


def _latest_batch_id(session: Session) -> uuid.UUID | None:
    """match_candidates is append-only: every matching-engine run adds a new
    batch rather than replacing the last one (see MatchCandidate docstring).
    Only the most recent batch reflects current, authoritative pair
    resolutions — older batches are audit history, not something to merge
    counts across."""
    return session.execute(
        select(MatchCandidate.batch_id).order_by(MatchCandidate.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _resolved_statuses(session: Session) -> dict[uuid.UUID, PairStatus]:
    batch_id = _latest_batch_id(session)
    candidates = (
        session.execute(select(MatchCandidate).where(MatchCandidate.batch_id == batch_id))
        .scalars()
        .all()
        if batch_id
        else []
    )
    adjudications = {
        a.match_candidate_id: a for a in session.execute(select(LlmAdjudication)).scalars().all()
    }
    reviews = {
        r.match_candidate_id: r for r in session.execute(select(HumanReview)).scalars().all()
    }
    return {c.id: resolve_pair(c, adjudications.get(c.id), reviews.get(c.id)) for c in candidates}


@app.get("/")
def dashboard(request: Request):
    session = _session()
    try:
        statuses = _resolved_statuses(session)
        status_counts = {status: 0 for status in PairStatus}
        for status in statuses.values():
            status_counts[status] += 1

        golden_vendor_count = session.query(GoldenVendor).count()
        record_count = session.query(NormalizedVendorRecord).count()

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "status_counts": status_counts,
                "golden_vendor_count": golden_vendor_count,
                "record_count": record_count,
            },
        )
    finally:
        session.close()


@app.get("/review")
def review_queue(request: Request):
    session = _session()
    try:
        statuses = _resolved_statuses(session)
        batch_id = _latest_batch_id(session)
        candidates_by_id = {
            c.id: c
            for c in session.execute(
                select(MatchCandidate).where(MatchCandidate.batch_id == batch_id)
            )
            .scalars()
            .all()
        }
        adjudications = {
            a.match_candidate_id: a
            for a in session.execute(select(LlmAdjudication)).scalars().all()
        }
        records_by_id = {
            r.id: r for r in session.execute(select(NormalizedVendorRecord)).scalars().all()
        }

        pending = [
            {
                "candidate": candidates_by_id[cid],
                "record_a": records_by_id[candidates_by_id[cid].record_id_1],
                "record_b": records_by_id[candidates_by_id[cid].record_id_2],
                "adjudication": adjudications.get(cid),
            }
            for cid, status in statuses.items()
            if status == PairStatus.NEEDS_REVIEW
        ]

        return templates.TemplateResponse(request, "review.html", {"pending": pending})
    finally:
        session.close()


@app.post("/review/{candidate_id}/decide")
def decide(
    candidate_id: str,
    decision: str = Form(...),
    reviewer: str = Form(...),
    note: str | None = Form(None),
):
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    session = _session()
    try:
        parsed_id = uuid.UUID(candidate_id)
        already_reviewed = session.execute(
            select(HumanReview).where(HumanReview.match_candidate_id == parsed_id)
        ).scalar_one_or_none()
        if already_reviewed is None:
            session.add(
                HumanReview(
                    match_candidate_id=parsed_id, decision=decision, reviewer=reviewer, note=note
                )
            )
            session.commit()
            rebuild_golden_vendors(session)
    finally:
        session.close()

    return RedirectResponse(url="/review", status_code=303)


@app.get("/vendors")
def vendor_list(request: Request):
    session = _session()
    try:
        vendors = (
            session.execute(select(GoldenVendor).order_by(GoldenVendor.member_count.desc()))
            .scalars()
            .all()
        )
        return templates.TemplateResponse(request, "vendors.html", {"vendors": vendors[:200]})
    finally:
        session.close()


@app.get("/vendors/{vendor_id}")
def vendor_detail(request: Request, vendor_id: str):
    session = _session()
    try:
        vendor = session.get(GoldenVendor, uuid.UUID(vendor_id))
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
        return templates.TemplateResponse(
            request, "vendor_detail.html", {"vendor": vendor, "members": members}
        )
    finally:
        session.close()
