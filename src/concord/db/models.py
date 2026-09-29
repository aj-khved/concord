import datetime
import uuid

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_GOLDEN_VENDOR_FK_NAME = "fk_normalized_vendor_records_golden_vendor_id"


class Base(DeclarativeBase):
    pass


class RawVendorRecord(Base):
    """Append-only landing zone: one row per record per ingestion run, exactly
    as read from the source. Never updated or deduplicated — it's the audit
    trail of what a source actually said at a point in time."""

    __tablename__ = "raw_vendor_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source: Mapped[str] = mapped_column(String(1))
    source_record_id: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB)
    loaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class NormalizedVendorRecord(Base):
    """Current-state canonical record per (source, source_record_id).
    Upserted on every ingestion run — re-running the same input updates
    these rows rather than duplicating them."""

    __tablename__ = "normalized_vendor_records"
    __table_args__ = (UniqueConstraint("source", "source_record_id", name="uq_source_record"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(1))
    source_record_id: Mapped[str] = mapped_column(String(50))
    legal_name: Mapped[str] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )
    golden_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("golden_vendors.id", name=_GOLDEN_VENDOR_FK_NAME),
        nullable=True,
    )


class MatchCandidate(Base):
    """Output of one matching-engine run for one candidate pair. Append-only
    per batch (like raw_vendor_records) — re-running matching produces a new
    batch rather than overwriting prior results, so past runs stay auditable."""

    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("batch_id", "record_id_1", "record_id_2", name="uq_match_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    record_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
    )
    record_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
    )
    score: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String(20))
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class LlmAdjudication(Base):
    """One LLM judgment for one match_candidate. Append-only and keyed so a
    candidate is only ever adjudicated once (idempotency, and cost control —
    re-running the adjudication script never re-pays for a pair it already
    has an answer for)."""

    __tablename__ = "llm_adjudications"
    __table_args__ = (UniqueConstraint("match_candidate_id", name="uq_adjudicated_candidate"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_candidates.id")
    )
    model: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class HumanReview(Base):
    """One reviewer decision for one match_candidate. A human decision is
    final — it overrides the deterministic engine's tier and any LLM
    adjudication (see concord/review/resolution.py). Append-only and unique
    per candidate: a pair is only ever decided by a human once."""

    __tablename__ = "human_reviews"
    __table_args__ = (UniqueConstraint("match_candidate_id", name="uq_reviewed_candidate"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_candidates.id")
    )
    decision: Mapped[str] = mapped_column(String(10))  # "approve" or "reject"
    reviewer: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class GoldenVendor(Base):
    """The reconciled vendor master (FR8). Rebuilt from scratch on every
    build_golden_vendors run (see concord/golden/builder.py) — this table is
    a materialized view of the current match decisions, not a source of
    truth in its own right."""

    __tablename__ = "golden_vendors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class DataQualityRun(Base):
    """One row per ingestion run, summarizing pass/fail counts and the
    breakdown of issue types found (FR11)."""

    __tablename__ = "data_quality_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source: Mapped[str] = mapped_column(String(1))
    records_ingested: Mapped[int] = mapped_column(Integer)
    records_passed: Mapped[int] = mapped_column(Integer)
    records_failed: Mapped[int] = mapped_column(Integer)
    issue_counts: Mapped[dict] = mapped_column(JSON)
    run_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )
