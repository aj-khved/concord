from dataclasses import dataclass
from enum import StrEnum


@dataclass
class VendorRecordView:
    """Minimal shape blocking/scoring need from a normalized vendor record —
    decoupled from the SQLAlchemy model so matching logic can be unit tested
    without a database."""

    id: str
    source: str
    source_record_id: str
    legal_name: str
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    tax_id: str | None
    phone: str | None
    category: str | None


class MatchTier(StrEnum):
    AUTO_MERGE = "auto_merge"
    PENDING_REVIEW = "pending_review"
    AUTO_REJECT = "auto_reject"


@dataclass
class PairScore:
    score: float
    features: dict[str, float]


@dataclass
class MatchResult:
    record_id_1: str
    record_id_2: str
    score: float
    tier: MatchTier
    features: dict[str, float]
