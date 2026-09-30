"""Joins the risk feed (keyed by tax_id) to golden vendors. A real risk data
feed only ever keys by an external identifier like tax ID — never by our
internal golden_vendor_id — so an unmatched row is an expected, ordinary
outcome (e.g. a vendor missing a tax ID everywhere it appears), not an error.
"""

from dataclasses import dataclass


@dataclass
class GoldenVendorLike:
    id: str
    tax_id: str | None


@dataclass
class RiskFeedRow:
    tax_id: str
    legal_name: str
    sanctions_flag: bool
    country_risk_tier: str
    financial_stability_score: int
    notes: str


@dataclass
class JoinResult:
    matched: list[tuple[str, RiskFeedRow]]  # (golden_vendor_id, risk_row)
    unmatched_tax_ids: list[str]


def join_risk_feed_to_golden_vendors(
    risk_rows: list[RiskFeedRow], golden_vendors: list[GoldenVendorLike]
) -> JoinResult:
    golden_by_tax_id: dict[str, str] = {
        v.tax_id: v.id for v in golden_vendors if v.tax_id is not None
    }

    matched = []
    unmatched = []
    for row in risk_rows:
        golden_vendor_id = golden_by_tax_id.get(row.tax_id)
        if golden_vendor_id is not None:
            matched.append((golden_vendor_id, row))
        else:
            unmatched.append(row.tax_id)

    return JoinResult(matched=matched, unmatched_tax_ids=unmatched)
