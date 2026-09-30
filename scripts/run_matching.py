"""Run the M3 matching engine against normalized_vendor_records and persist
the results to match_candidates.

Usage:
    uv run python scripts/run_matching.py
"""

import uuid
from collections import Counter

from concord.db.models import MatchCandidate, NormalizedVendorRecord
from concord.db.session import get_session
from concord.matching.engine import run_matching
from concord.matching.schema import VendorRecordView
from concord.observability.pipeline_run import track_pipeline_run


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
    session = next(get_session())
    try:
        with track_pipeline_run(session, "matching") as run:
            rows = session.query(NormalizedVendorRecord).all()
            records = [_to_view(r) for r in rows]

            results = run_matching(records)

            batch_id = uuid.uuid4()
            session.add_all(
                MatchCandidate(
                    batch_id=batch_id,
                    record_id_1=uuid.UUID(r.record_id_1),
                    record_id_2=uuid.UUID(r.record_id_2),
                    score=r.score,
                    tier=r.tier.value,
                    features=r.features,
                )
                for r in results
            )
            session.commit()

            tier_counts = dict(Counter(r.tier.value for r in results))
            run.summary = {
                "batch_id": str(batch_id),
                "records_considered": len(records),
                "candidate_pairs": len(results),
                "tier_counts": tier_counts,
            }

        print(f"Batch: {batch_id}")
        print(f"Records considered: {len(records)}")
        print(f"Candidate pairs: {len(results)}")
        print(f"Tier breakdown: {tier_counts}")
    finally:
        session.close()
