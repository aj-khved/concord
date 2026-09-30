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
    """One LLM judgment for one record pair. Keyed by (record_id_1,
    record_id_2) -- the underlying pair identity -- NOT by match_candidate_id.
    match_candidates is append-only (a fresh row, with a fresh id, every time
    the matching engine re-runs), so keying by match_candidate_id would
    silently orphan every prior adjudication on each re-run, forcing costly
    re-adjudication of pairs that already have a perfectly good answer. This
    was a real bug, found by actually re-running the matching engine after
    M4/M5 and watching resolved pairs revert to needs_review."""

    __tablename__ = "llm_adjudications"
    __table_args__ = (UniqueConstraint("record_id_1", "record_id_2", name="uq_adjudicated_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
    )
    record_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
    )
    model: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )


class HumanReview(Base):
    """One reviewer decision for one record pair. Keyed by (record_id_1,
    record_id_2) for the same reason as LlmAdjudication above -- a human
    decision must survive re-running the matching engine, not just survive
    within one batch. A human decision is final: it overrides the
    deterministic engine's tier and any LLM adjudication (see
    concord/review/resolution.py)."""

    __tablename__ = "human_reviews"
    __table_args__ = (UniqueConstraint("record_id_1", "record_id_2", name="uq_reviewed_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
    )
    record_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_vendor_records.id")
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


class VendorRiskProfile(Base):
    """Risk data joined by tax_id (FR9), not by golden_vendor_id — golden_vendors
    is rebuilt from scratch on every change (new UUIDs each time, see
    GoldenVendor docstring), so a stored FK to it would break on every
    rebuild. tax_id is the stable, externally-meaningful key a real risk
    feed would actually use. Upserted per tax_id, like normalized_vendor_records."""

    __tablename__ = "vendor_risk_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tax_id: Mapped[str] = mapped_column(String(20), unique=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    sanctions_flag: Mapped[bool] = mapped_column()
    country_risk_tier: Mapped[str] = mapped_column(String(10))
    financial_stability_score: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(10))
    notes: Mapped[str] = mapped_column(String(1000))
    llm_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


class PipelineRun(Base):
    """One row per execution of any pipeline script (ingestion, matching,
    LLM adjudication, risk ingestion, risk summarization) — the concrete
    answer to "did this run, how long did it take, and what did it cost"
    (NFR: observability). `summary` holds run-type-specific details (record
    counts, tier breakdowns, token usage, estimated cost) as flexible JSON
    rather than a rigid schema, since each run type reports different things."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10))  # "success" or "failed"
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    summary: Mapped[dict] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)


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
