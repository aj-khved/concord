"""Blocking narrows ~4,900 records down to a manageable candidate-pair set
without comparing every record to every other record — naive all-pairs
comparison is O(n^2) and doesn't scale.

Two independent blocking keys are used because they catch different things:
- Postal code is an exact match and, in this dataset, identical across
  sources for the same real vendor — high-precision, high-recall blocking.
- Name-prefix + city is what makes the deliberately confusable non-duplicate
  pairs from M1 (same city, similar name, different postal code) actually
  reach the scoring stage — without it, blocking alone would trivially reject
  them and the scorer's precision would never be exercised against anything
  hard.

A record pair only needs to share ONE of these keys to become a candidate.
"""

from collections import defaultdict
from itertools import combinations

from concord.matching.schema import VendorRecordView
from concord.matching.text import core_name_tokens


def _name_block_key(legal_name: str) -> str:
    tokens = core_name_tokens(legal_name)
    return tokens[0] if tokens else ""


def generate_candidate_pairs(records: list[VendorRecordView]) -> set[tuple[str, str]]:
    postal_blocks: dict[str, list[str]] = defaultdict(list)
    name_city_blocks: dict[tuple[str, str], list[str]] = defaultdict(list)

    for r in records:
        if r.postal_code:
            postal_blocks[r.postal_code].append(r.id)
        name_key = _name_block_key(r.legal_name)
        if name_key and r.city:
            name_city_blocks[(r.city.lower(), name_key)].append(r.id)

    pairs: set[tuple[str, str]] = set()
    for block in [*postal_blocks.values(), *name_city_blocks.values()]:
        if len(block) < 2:
            continue
        for a, b in combinations(sorted(set(block)), 2):
            pairs.add((a, b))
    return pairs
