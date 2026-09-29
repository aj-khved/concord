from concord.normalization.quality import check_record, run_quality_checks
from concord.normalization.schema import CanonicalVendorRecord


def _valid_record(**overrides) -> CanonicalVendorRecord:
    defaults = dict(
        source="A",
        source_record_id="A-000001",
        legal_name="Acme Inc.",
        city="Springfield",
        state="IL",
        postal_code="62704",
        country="US",
        tax_id="123456789",
        phone="1234567890",
        category="Manufacturing",
    )
    defaults.update(overrides)
    return CanonicalVendorRecord(**defaults)


def test_valid_record_has_no_issues():
    assert check_record(_valid_record()) == []


def test_missing_tax_id_is_not_an_issue():
    # tax_id is legitimately absent in some real records (see quality.py docstring)
    assert check_record(_valid_record(tax_id=None)) == []


def test_missing_required_field_is_flagged():
    issues = check_record(_valid_record(legal_name=""))
    assert "missing_legal_name" in issues


def test_invalid_phone_length_is_flagged():
    issues = check_record(_valid_record(phone="123"))
    assert "invalid_phone_length" in issues


def test_invalid_postal_code_is_flagged():
    issues = check_record(_valid_record(postal_code="ABCDE"))
    assert "invalid_postal_code" in issues


def test_run_quality_checks_aggregates_counts():
    records = [
        _valid_record(source_record_id="A-1"),
        _valid_record(source_record_id="A-2", legal_name=""),
        _valid_record(source_record_id="A-3", phone="123"),
    ]
    report = run_quality_checks(records)
    assert report.records_checked == 3
    assert report.records_passed == 1
    assert report.records_failed == 2
    assert report.issue_counts == {"missing_legal_name": 1, "invalid_phone_length": 1}
