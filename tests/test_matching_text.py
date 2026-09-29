from concord.matching.text import normalized_name, normalized_street


def test_normalized_name_strips_legal_suffix_variants():
    assert normalized_name("Acme, Inc.") == "acme"
    assert normalized_name("ACME INCORPORATED") == "acme"
    assert normalized_name("Acme LLC") == "acme"


def test_normalized_name_preserves_distinct_names():
    assert normalized_name("Acme Consulting") != normalized_name("Acme Group")


def test_normalized_street_abbreviates_consistently():
    assert normalized_street("100 Main Street") == normalized_street("100 Main St")


def test_normalized_street_handles_none():
    assert normalized_street(None) == ""
