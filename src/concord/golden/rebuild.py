"""Orchestrates a full golden-vendor rebuild against the database: reads
every match_candidate's resolved status (concord.review.resolution) and
recomputes clusters from scratch via concord.golden.builder.

Called both by scripts/build_golden_vendors.py and by the review UI after
each human decision — cheap enough at this data volume (~5,000 records) to
run synchronously and give the reviewer immediate feedback."""

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from concord.db.models import (
    GoldenVendor,
    HumanReview,
    LlmAdjudication,
    MatchCandidate,
    NormalizedVendorRecord,
)
from concord.golden.builder import build_golden_vendors
from concord.matching.pair_key import pair_key
from concord.matching.schema import VendorRecordView
from concord.review.resolution import PairStatus, resolve_pair


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


@dataclass
class RebuildSummary:
    golden_vendor_count: int
    record_count: int
    largest_cluster_size: int


def rebuild_golden_vendors(session: Session) -> RebuildSummary:
    records = session.execute(select(NormalizedVendorRecord)).scalars().all()

    # match_candidates is append-only (one batch per matching-engine run) —
    # only the latest batch reflects current pair resolutions.
    latest_batch_id = session.execute(
        select(MatchCandidate.batch_id).order_by(MatchCandidate.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    candidates = (
        session.execute(select(MatchCandidate).where(MatchCandidate.batch_id == latest_batch_id))
        .scalars()
        .all()
        if latest_batch_id
        else []
    )
    adjudications_by_pair = {
        pair_key(a.record_id_1, a.record_id_2): a
        for a in session.execute(select(LlmAdjudication)).scalars().all()
    }
    reviews_by_pair = {
        pair_key(r.record_id_1, r.record_id_2): r
        for r in session.execute(select(HumanReview)).scalars().all()
    }

    match_pairs: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = pair_key(candidate.record_id_1, candidate.record_id_2)
        status = resolve_pair(candidate, adjudications_by_pair.get(key), reviews_by_pair.get(key))
        if status == PairStatus.MATCH:
            match_pairs.add((str(candidate.record_id_1), str(candidate.record_id_2)))

    views = [_to_view(r) for r in records]
    builds = build_golden_vendors(views, match_pairs)

    # Full rebuild, not a patch: detach old references, drop old golden
    # vendors, insert fresh ones. Simpler and safer than incremental updates
    # at this data volume — see module docstring.
    session.execute(update(NormalizedVendorRecord).values(golden_vendor_id=None))
    session.execute(delete(GoldenVendor))
    session.flush()

    records_by_id = {str(r.id): r for r in records}
    for build in builds:
        golden = GoldenVendor(member_count=len(build.member_ids), **build.canonical_fields)
        session.add(golden)
        session.flush()  # assign golden.id before using it below
        for member_id in build.member_ids:
            records_by_id[member_id].golden_vendor_id = golden.id

    session.commit()

    largest = max((len(b.member_ids) for b in builds), default=0)
    return RebuildSummary(
        golden_vendor_count=len(builds), record_count=len(records), largest_cluster_size=largest
    )
