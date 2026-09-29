import datetime
import uuid

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
