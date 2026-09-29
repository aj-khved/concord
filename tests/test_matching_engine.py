from concord.matching.engine import run_matching, tier_for_score
from concord.matching.schema import MatchTier, VendorRecordView


def _record(**overrides) -> VendorRecordView:
    defaults = dict(
        id="id-1",
        source="A",
        source_record_id="A-1",
        legal_name="Acme Inc.",
        address_line1="100 Main St",
        city="Springfield",
        state="IL",
        postal_code="62704",
        country="US",
        tax_id="123456789",
        phone="1234567890",
        category="Manufacturing",
    )
    defaults.update(overrides)
    return VendorRecordView(**defaults)


def test_tier_thresholds():
    assert tier_for_score(0.95) == MatchTier.AUTO_MERGE
    assert tier_for_score(0.90) == MatchTier.AUTO_MERGE
    assert tier_for_score(0.70) == MatchTier.PENDING_REVIEW
    assert tier_for_score(0.55) == MatchTier.AUTO_REJECT
    assert tier_for_score(0.10) == MatchTier.AUTO_REJECT


def test_run_matching_finds_true_duplicate_and_rejects_unrelated_record():
    duplicate_a = _record(id="1", source="A", source_record_id="A-1")
    duplicate_b = _record(id="2", source="B", source_record_id="B-1")
    unrelated = _record(
        id="3",
        source="C",
        source_record_id="C-1",
        legal_name="Globex Corp",
        postal_code="10001",
        city="New York",
        phone="9998887777",
        tax_id="987654321",
    )

    results = run_matching([duplicate_a, duplicate_b, unrelated])
    result_by_pair = {frozenset({r.record_id_1, r.record_id_2}): r for r in results}

    assert result_by_pair[frozenset({"1", "2"})].tier == MatchTier.AUTO_MERGE
    # unrelated record shares no blocking key with the others, so it should
    # never even become a candidate pair
    assert frozenset({"1", "3"}) not in result_by_pair
    assert frozenset({"2", "3"}) not in result_by_pair
