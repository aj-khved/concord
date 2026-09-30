"""Pydantic response models for the JSON REST API (FR10). Kept separate
from app.py's HTML routes, which pass plain dicts to Jinja2 templates and
don't need this validation/serialization layer."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class SourceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    source_record_id: str
    legal_name: str
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None


class RiskProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_level: str
    risk_score: int
    sanctions_flag: bool
    country_risk_tier: str
    financial_stability_score: int
    notes: str
    llm_summary: str | None


class VendorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    city: str | None
    category: str | None
    member_count: int
    risk_level: str | None = None


class VendorListOut(BaseModel):
    total: int
    items: list[VendorSummary]


class VendorDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    tax_id: str | None
    phone: str | None
    category: str | None
    member_count: int
    risk_profile: RiskProfileOut | None
    members: list[SourceRecordOut]


class PendingReviewItemOut(BaseModel):
    match_candidate_id: uuid.UUID
    score: float
    record_a: SourceRecordOut
    record_b: SourceRecordOut
    llm_outcome: str | None
    llm_confidence: float | None
    llm_rationale: str | None


class ReviewDecisionRequest(BaseModel):
    decision: str
    reviewer: str
    note: str | None = None


class ReviewDecisionResponse(BaseModel):
    match_candidate_id: uuid.UUID
    decision: str
    already_reviewed: bool


class PipelineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_type: str
    status: str
    started_at: datetime.datetime
    finished_at: datetime.datetime
    duration_ms: int
    summary: dict
    error_message: str | None


class IngestionTriggerResponse(BaseModel):
    batch_id: uuid.UUID
    per_source: dict
