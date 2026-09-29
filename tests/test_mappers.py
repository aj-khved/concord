from concord.normalization.mappers import (
    digits_only,
    map_source_a,
    map_source_b,
    map_source_c,
    normalize_country,
    normalize_phone,
    parse_full_address,
)


def test_normalize_country_aliases():
    assert normalize_country("USA") == "US"
    assert normalize_country("United States") == "US"
    assert normalize_country("us") == "US"
    assert normalize_country(None) is None


def test_normalize_phone_strips_country_code():
    assert normalize_phone("+1 103 413 1647") == "1034131647"
    assert normalize_phone("(386) 379-4026") == "3863794026"
    assert normalize_phone(None) is None


def test_digits_only_returns_none_for_empty():
    assert digits_only("") is None
    assert digits_only(None) is None
    assert digits_only("12-3456789") == "123456789"


def test_parse_full_address_happy_path():
    result = parse_full_address("192 Frank Light Suite 835, East Lydiamouth, MO 35594, USA")
    assert result == {
        "street": "192 Frank Light Suite 835",
        "city": "East Lydiamouth",
        "state": "MO",
        "postal_code": "35594",
        "country": "USA",
    }


def test_parse_full_address_unparseable_returns_all_none():
    result = parse_full_address("not a real address")
    assert all(v is None for v in result.values())


def test_map_source_a():
    raw = {
        "vendor_id_src": "A-000001",
        "legal_name": "MARTIN-KELLY",
        "address_line1": "192 Frank Light Suite 835",
        "city": "East Lydiamouth",
        "state": "MO",
        "postal_code": "35594",
        "country": "United States",
        "tax_id": "36-2950628",
        "phone": "139-537-6724",
        "category": "Professional Services",
    }
    record = map_source_a(raw, "A-000001")
    assert record.source_record_id == "A-000001"
    assert record.tax_id == "362950628"
    assert record.phone == "1395376724"
    assert record.country == "US"


def test_map_source_b_missing_tax_id():
    raw = {
        "VendorName": "Johnson L.L.C.",
        "FullAddress": "21819 Johnson Course, East William, AK 74064, USA",
        "EIN": "",
        "ContactPhone": "(386) 379-4026",
        "Category": "Logistics",
    }
    record = map_source_b(raw, "B-000001")
    assert record.tax_id is None
    assert record.city == "East William"
    assert record.phone == "3863794026"


def test_map_source_c():
    raw = {
        "recordId": "C-000001",
        "companyName": "Moore-Bernard",
        "location": {
            "street": "16155 Roman Stream Suite 816",
            "city": "New Kellystad",
            "region": "OK",
            "postalCode": "25704",
            "country": "USA",
        },
        "identifiers": {"taxId": "12-6855092"},
        "contact": {"phone": "+1 103 413 1647"},
        "vertical": "Construction",
    }
    record = map_source_c(raw, "C-000001")
    assert record.phone == "1034131647"
    assert record.tax_id == "126855092"
    assert record.category == "Construction"
