"""Ties ingestion, normalization, and data-quality checking into one run.

Raw records are appended (audit log). Canonical records are upserted keyed
on (source, source_record_id), so re-running the same input file updates
existing rows instead of duplicating them (idempotency, per the charter's
non-functional requirements).
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from concord.db.models import DataQualityRun, NormalizedVendorRecord, RawVendorRecord
from concord.ingestion.readers import READERS
from concord.normalization.mappers import MAPPERS
from concord.normalization.quality import run_quality_checks

DEFAULT_FILENAMES = {
    "A": "source_a_erp_export.csv",
    "B": "source_b_manual_upload.csv",
    "C": "source_c_partner_feed.json",
}


@dataclass
class IngestionSummary:
    batch_id: uuid.UUID
    per_source: dict[str, dict]


def run_ingestion(data_dir: Path, session: Session) -> IngestionSummary:
    batch_id = uuid.uuid4()
    per_source: dict[str, dict] = {}

    for source, filename in DEFAULT_FILENAMES.items():
        path = data_dir / filename
        raw_records = READERS[source](path)
        mapper = MAPPERS[source]

        canonical_records = [mapper(rr.payload, rr.source_record_id) for rr in raw_records]
        quality_report = run_quality_checks(canonical_records)

        session.add_all(
            RawVendorRecord(
                batch_id=batch_id,
                source=rr.source,
                source_record_id=rr.source_record_id,
                payload=rr.payload,
            )
            for rr in raw_records
        )

        _upsert_canonical_records(session, canonical_records)

        session.add(
            DataQualityRun(
                batch_id=batch_id,
                source=source,
                records_ingested=quality_report.records_checked,
                records_passed=quality_report.records_passed,
                records_failed=quality_report.records_failed,
                issue_counts=quality_report.issue_counts,
            )
        )

        per_source[source] = quality_report.as_dict()

    session.commit()
    return IngestionSummary(batch_id=batch_id, per_source=per_source)


def _upsert_canonical_records(session: Session, records: list) -> None:
    if not records:
        return
    rows = [r.model_dump() for r in records]
    stmt = insert(NormalizedVendorRecord).values(rows)
    update_columns = {
        col: getattr(stmt.excluded, col)
        for col in rows[0]
        if col not in ("source", "source_record_id")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "source_record_id"],
        set_=update_columns,
    )
    session.execute(stmt)
