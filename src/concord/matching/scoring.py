"""Deterministic similarity scoring for a candidate pair.

Each feature is only included if both records actually have that field —
e.g. tax_id is legitimately missing for ~15% of Source B records, so a
missing tax_id must not silently drag the score down. The final score is a
weighted average over whichever features were actually available, not a
fixed formula that always includes every weight. This keeps every decision
auditable: for any pair, you can point at exactly which features fired and
by how much, rather than a black-box number.
"""

from rapidfuzz import fuzz

from concord.matching.schema import PairScore, VendorRecordView
from concord.matching.text import normalized_name, normalized_street

FEATURE_WEIGHTS: dict[str, float] = {
    "name": 0.40,
    "address": 0.15,
    "postal_code": 0.20,
    "phone": 0.15,
    "tax_id": 0.15,
    "category": 0.10,
}

AUTO_MERGE_THRESHOLD = 0.90
AUTO_REJECT_THRESHOLD = 0.55


def score_pair(a: VendorRecordView, b: VendorRecordView) -> PairScore:
    features: dict[str, float] = {
        "name": fuzz.token_sort_ratio(normalized_name(a.legal_name), normalized_name(b.legal_name))
        / 100
    }

    if a.address_line1 and b.address_line1:
        features["address"] = (
            fuzz.token_sort_ratio(
                normalized_street(a.address_line1), normalized_street(b.address_line1)
            )
            / 100
        )

    if a.postal_code and b.postal_code:
        features["postal_code"] = 1.0 if a.postal_code == b.postal_code else 0.0

    if a.phone and b.phone:
        features["phone"] = 1.0 if a.phone == b.phone else 0.0

    if a.tax_id and b.tax_id:
        features["tax_id"] = 1.0 if a.tax_id == b.tax_id else 0.0

    if a.category and b.category:
        features["category"] = 1.0 if a.category == b.category else 0.0

    weight_sum = sum(FEATURE_WEIGHTS[k] for k in features)
    score = (
        sum(FEATURE_WEIGHTS[k] * v for k, v in features.items()) / weight_sum if weight_sum else 0.0
    )

    return PairScore(score=score, features=features)
