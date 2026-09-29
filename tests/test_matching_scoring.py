from concord.matching.schema import VendorRecordView
from concord.matching.scoring import score_pair


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


def test_identical_records_score_near_one():
    a = _record()
    b = _record(id="id-2", source="B", source_record_id="B-1")
    result = score_pair(a, b)
    assert result.score > 0.99


def test_missing_tax_id_excludes_feature_rather_than_penalizing():
    a = _record(tax_id=None)
    b = _record(id="id-2", tax_id="123456789")
    result = score_pair(a, b)
    assert "tax_id" not in result.features
    # score should still be high since every other field matches
    assert result.score > 0.9


def test_different_postal_code_and_name_lowers_score():
    a = _record(legal_name="Acme Consulting", postal_code="62704")
    b = _record(id="id-2", legal_name="Acme Group", postal_code="99999")
    result = score_pair(a, b)
    assert result.features["postal_code"] == 0.0
    assert result.score < 0.7


def test_completely_unrelated_records_score_low():
    a = _record(
        legal_name="Acme Inc.",
        postal_code="62704",
        phone="1234567890",
        tax_id="123456789",
        category="Manufacturing",
    )
    b = _record(
        id="id-2",
        legal_name="Globex Corp",
        postal_code="10001",
        phone="9998887777",
        tax_id="987654321",
        category="Construction",
    )
    result = score_pair(a, b)
    assert result.score < 0.4
