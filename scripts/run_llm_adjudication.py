"""Run LLM adjudication (M4) against the latest matching batch's
pending_review pairs.

Only calls the LLM for pairs that don't already have an adjudication
(idempotent — safe to re-run) and stops after settings.llm_max_calls_per_run
calls (cost cap).

Requires ANTHROPIC_API_KEY in your local .env (see .env.example).

Usage:
    uv run python scripts/run_llm_adjudication.py
"""

import anthropic
from sqlalchemy import select

from concord.config import settings
from concord.db.models import LlmAdjudication, MatchCandidate, NormalizedVendorRecord
from concord.db.session import get_session
from concord.llm.adjudicator import adjudicate_pair
from concord.matching.schema import VendorRecordView


def _to_view(row: NormalizedVendorRecord) -> VendorRecordView:
    return VendorRecordView(
        id=str(row.id),
        source=row.source,
        source_record_id=row.source_record_id,
        legal_name=row.legal_name,
        address_line1=row.address_line1,
        city=row.city,
        state=row.state,
        postal_code=row.postal_code,
        country=row.country,
        tax_id=row.tax_id,
        phone=row.phone,
        category=row.category,
    )


if __name__ == "__main__":
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — add it to your local .env first.")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, base_url=settings.llm_base_url)

    session = next(get_session())
    try:
        latest_batch = session.execute(
            select(MatchCandidate.batch_id).order_by(MatchCandidate.created_at.desc()).limit(1)
        ).scalar_one()

        already_adjudicated = {
            row.match_candidate_id
            for row in session.execute(select(LlmAdjudication.match_candidate_id)).scalars().all()
        }

        pending = (
            session.execute(
                select(MatchCandidate).where(
                    MatchCandidate.batch_id == latest_batch,
                    MatchCandidate.tier == "pending_review",
                )
            )
            .scalars()
            .all()
        )
        not_yet_adjudicated = [c for c in pending if c.id not in already_adjudicated]
        to_adjudicate = not_yet_adjudicated[: settings.llm_max_calls_per_run]

        records_by_id = {
            row.id: _to_view(row)
            for row in session.execute(select(NormalizedVendorRecord)).scalars().all()
        }

        print(f"Pending-review pairs: {len(pending)}")
        print(f"Already adjudicated (skipped): {len(pending) - len(not_yet_adjudicated)}")
        print(
            f"Adjudicating now (capped at {settings.llm_max_calls_per_run}): {len(to_adjudicate)}"
        )
        deferred = len(not_yet_adjudicated) - len(to_adjudicate)
        if deferred:
            print(f"Deferred to a future run due to cap: {deferred}")

        for candidate in to_adjudicate:
            record_a = records_by_id[candidate.record_id_1]
            record_b = records_by_id[candidate.record_id_2]
            result = adjudicate_pair(client, record_a, record_b, model=settings.llm_model)

            session.add(
                LlmAdjudication(
                    match_candidate_id=candidate.id,
                    model=settings.llm_model,
                    outcome=result.outcome.value,
                    confidence=result.confidence,
                    rationale=result.rationale,
                )
            )
            summary = f"{result.outcome.value} ({result.confidence:.2f})"
            print(f"  {record_a.legal_name!r} <-> {record_b.legal_name!r}: {summary}")

        session.commit()
    finally:
        session.close()
