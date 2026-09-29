from concord.golden.builder import build_golden_vendors
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


def test_unrelated_records_form_singleton_clusters():
    a = _record(id="1")
    b = _record(id="2", source="B", source_record_id="B-1")
    builds = build_golden_vendors([a, b], match_pairs=set())
    assert len(builds) == 2
    assert {frozenset(b.member_ids) for b in builds} == {frozenset({"1"}), frozenset({"2"})}


def test_directly_matched_pair_forms_one_cluster():
    a = _record(id="1")
    b = _record(id="2", source="B", source_record_id="B-1")
    builds = build_golden_vendors([a, b], match_pairs={("1", "2")})
    assert len(builds) == 1
    assert set(builds[0].member_ids) == {"1", "2"}


def test_transitive_matches_merge_into_one_cluster():
    # A matches B, B matches C -- A and C were never directly compared but
    # must still end up in the same golden vendor.
    a = _record(id="1", source="A", source_record_id="A-1")
    b = _record(id="2", source="B", source_record_id="B-1")
    c = _record(id="3", source="C", source_record_id="C-1")
    builds = build_golden_vendors([a, b, c], match_pairs={("1", "2"), ("2", "3")})
    assert len(builds) == 1
    assert set(builds[0].member_ids) == {"1", "2", "3"}


def test_representative_prefers_most_complete_record():
    incomplete = _record(id="1", tax_id=None, phone=None)
    complete = _record(id="2", source="B", source_record_id="B-1")
    builds = build_golden_vendors([incomplete, complete], match_pairs={("1", "2")})
    assert builds[0].canonical_fields["tax_id"] == "123456789"
    assert builds[0].canonical_fields["phone"] == "1234567890"
