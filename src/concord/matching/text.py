"""Text normalization shared by blocking and scoring. Kept separate from
concord.normalization.mappers — that module undoes source-specific messiness
during ingestion; this module normalizes further, specifically to make two
records comparable regardless of which source they came from."""

import re

_LEGAL_SUFFIX_TOKENS = {
    "inc",
    "incorporated",
    "llc",
    "corp",
    "corporation",
    "ltd",
    "limited",
    "co",
    "company",
    "group",
    "grp",
}

_STREET_ABBR = {
    "street": "st",
    "avenue": "ave",
    "boulevard": "blvd",
    "drive": "dr",
    "lane": "ln",
    "road": "rd",
    "court": "ct",
    "circle": "cir",
}


def core_name_tokens(name: str) -> list[str]:
    """Lowercase, alphanumeric-only tokens with legal-entity suffixes removed,
    e.g. "Acme, Inc." and "ACME INCORPORATED" both -> ["acme"]."""
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    return [t for t in tokens if t not in _LEGAL_SUFFIX_TOKENS]


def normalized_name(name: str) -> str:
    return " ".join(core_name_tokens(name))


def normalized_street(address: str | None) -> str:
    if not address:
        return ""
    words = address.lower().replace(",", "").split()
    return " ".join(_STREET_ABBR.get(w, w) for w in words)
