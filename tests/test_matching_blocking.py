from concord.matching.blocking import generate_candidate_pairs
from concord.matching.schema import VendorRecordView


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


def test_shared_postal_code_produces_a_candidate_pair():
    a = _record(id="1", postal_code="62704", legal_name="Totally Different Name")
    b = _record(id="2", postal_code="62704", legal_name="Another Unrelated Co")
    pairs = generate_candidate_pairs([a, b])
    assert ("1", "2") in pairs


def test_shared_name_and_city_produces_a_candidate_pair_despite_different_postal_code():
    a = _record(id="1", postal_code="62704", city="Springfield", legal_name="Acme Group")
    b = _record(id="2", postal_code="99999", city="Springfield", legal_name="Acme Solutions")
    pairs = generate_candidate_pairs([a, b])
    assert ("1", "2") in pairs


def test_unrelated_records_produce_no_candidate_pair():
    a = _record(id="1", postal_code="62704", city="Springfield", legal_name="Acme Inc.")
    b = _record(id="2", postal_code="10001", city="New York", legal_name="Globex Corp")
    pairs = generate_candidate_pairs([a, b])
    assert len(pairs) == 0


def test_singleton_blocks_produce_no_pairs():
    a = _record(id="1", postal_code="62704", city="Springfield", legal_name="Acme Inc.")
    pairs = generate_candidate_pairs([a])
    assert pairs == set()
