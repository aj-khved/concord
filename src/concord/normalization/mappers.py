"""Map each source's raw payload into the canonical schema, applying the
field-level cleaning needed to undo that source's specific messiness
patterns (see docs/data_messiness_spec.md for what each source does)."""

import re

from concord.normalization.schema import CanonicalVendorRecord

_COUNTRY_ALIASES = {"US": "US", "USA": "US", "UNITED STATES": "US"}

_FULL_ADDRESS_RE = re.compile(
    r"^(?P<street>.+), (?P<city>.+), (?P<state>[A-Z]{2}) "
    r"(?P<postal_code>\d{5}(?:-\d{4})?), (?P<country>.+)$"
)


def clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split()).strip()
    return value or None


def digits_only(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(c for c in value if c.isdigit())
    return digits or None


def normalize_phone(value: str | None) -> str | None:
    digits = digits_only(value)
    if digits and len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]  # strip US country code, e.g. "+1 103 413 1647"
    return digits


def normalize_country(value: str | None) -> str | None:
    cleaned = clean_str(value)
    if cleaned is None:
        return None
    return _COUNTRY_ALIASES.get(cleaned.upper(), cleaned.upper())


def parse_full_address(full_address: str | None) -> dict[str, str | None]:
    """Source B stores one combined address string instead of split fields.
    Returns all-None if the format doesn't match rather than raising —
    an unparseable address is a data-quality issue, not a crash."""
    empty = {"street": None, "city": None, "state": None, "postal_code": None, "country": None}
    if not full_address:
        return empty
    match = _FULL_ADDRESS_RE.match(full_address.strip())
    if not match:
        return empty
    return match.groupdict()


def map_source_a(raw: dict, source_record_id: str) -> CanonicalVendorRecord:
    return CanonicalVendorRecord(
        source="A",
        source_record_id=source_record_id,
        legal_name=clean_str(raw.get("legal_name")) or "",
        address_line1=clean_str(raw.get("address_line1")),
        city=clean_str(raw.get("city")),
        state=clean_str(raw.get("state")),
        postal_code=clean_str(raw.get("postal_code")),
        country=normalize_country(raw.get("country")),
        tax_id=digits_only(raw.get("tax_id")),
        phone=normalize_phone(raw.get("phone")),
        category=clean_str(raw.get("category")),
    )


def map_source_b(raw: dict, source_record_id: str) -> CanonicalVendorRecord:
    address = parse_full_address(raw.get("FullAddress"))
    return CanonicalVendorRecord(
        source="B",
        source_record_id=source_record_id,
        legal_name=clean_str(raw.get("VendorName")) or "",
        address_line1=clean_str(address["street"]),
        city=clean_str(address["city"]),
        state=clean_str(address["state"]),
        postal_code=clean_str(address["postal_code"]),
        country=normalize_country(address["country"]),
        tax_id=digits_only(raw.get("EIN")),
        phone=normalize_phone(raw.get("ContactPhone")),
        category=clean_str(raw.get("Category")),
    )


def map_source_c(raw: dict, source_record_id: str) -> CanonicalVendorRecord:
    location = raw.get("location", {})
    return CanonicalVendorRecord(
        source="C",
        source_record_id=source_record_id,
        legal_name=clean_str(raw.get("companyName")) or "",
        address_line1=clean_str(location.get("street")),
        city=clean_str(location.get("city")),
        state=clean_str(location.get("region")),
        postal_code=clean_str(location.get("postalCode")),
        country=normalize_country(location.get("country")),
        tax_id=digits_only(raw.get("identifiers", {}).get("taxId")),
        phone=normalize_phone(raw.get("contact", {}).get("phone")),
        category=clean_str(raw.get("vertical")),
    )


MAPPERS = {"A": map_source_a, "B": map_source_b, "C": map_source_c}
