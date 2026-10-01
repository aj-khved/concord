"""Minimal server-rendered review UI (M5) plus a JSON REST API (M7/FR10) —
concord.api.rest. Deliberately not a React SPA for the UI — see
docs/charter.md §9.6 for why: proving the review workflow matters more
right now than frontend polish."""

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from concord.api.rest import router as rest_router
from concord.api.review_service import (
    CandidateNotFoundError,
    InvalidDecisionError,
    adjudications_by_pair,
    decide_pair,
    latest_batch_id,
    resolved_statuses,
)
from concord.db.models import (
    GoldenVendor,
    MatchCandidate,
    NormalizedVendorRecord,
    VendorRiskProfile,
)
from concord.db.session import get_session
from concord.matching.pair_key import pair_key
from concord.observability.logging_config import configure_logging
from concord.review.resolution import PairStatus

configure_logging()
logger = logging.getLogger("concord.api")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Concord")

# Allows the portfolio website (any origin) to fetch read-only data from
# /api/* client-side, e.g. to show live stats on a project page. Deliberately
# scoped to GET only -- the data here is already fully public with no auth,
# so permissive read access is low-risk, but a browser should still never be
# able to cross-origin POST a review decision or trigger a pipeline run from
# an arbitrary third-party page.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "http_request",
        extra={
            "extra_fields": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        },
    )
    return response


def _session() -> Session:
    return next(get_session())


@app.get("/")
def dashboard(request: Request):
    session = _session()
    try:
        statuses = resolved_statuses(session)
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
        statuses = resolved_statuses(session)
        batch_id = latest_batch_id(session)
        candidates_by_id = {
            c.id: c
            for c in session.execute(
                select(MatchCandidate).where(MatchCandidate.batch_id == batch_id)
            )
            .scalars()
            .all()
        }
        adjudications = adjudications_by_pair(session)
        records_by_id = {
            r.id: r for r in session.execute(select(NormalizedVendorRecord)).scalars().all()
        }

        pending = [
            {
                "candidate": candidates_by_id[cid],
                "record_a": records_by_id[candidates_by_id[cid].record_id_1],
                "record_b": records_by_id[candidates_by_id[cid].record_id_2],
                "adjudication": adjudications.get(
                    pair_key(candidates_by_id[cid].record_id_1, candidates_by_id[cid].record_id_2)
                ),
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
    session = _session()
    try:
        try:
            decide_pair(session, uuid.UUID(candidate_id), decision, reviewer, note)
        except InvalidDecisionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CandidateNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        )[:200]
        risk_by_tax_id = {
            p.tax_id: p for p in session.execute(select(VendorRiskProfile)).scalars().all()
        }
        rows = [(v, risk_by_tax_id.get(v.tax_id)) for v in vendors]
        return templates.TemplateResponse(request, "vendors.html", {"rows": rows})
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
        risk_profile = (
            session.execute(
                select(VendorRiskProfile).where(VendorRiskProfile.tax_id == vendor.tax_id)
            ).scalar_one_or_none()
            if vendor.tax_id
            else None
        )
        return templates.TemplateResponse(
            request,
            "vendor_detail.html",
            {"vendor": vendor, "members": members, "risk_profile": risk_profile},
        )
    finally:
        session.close()


app.include_router(rest_router, prefix="/api")
