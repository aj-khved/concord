"""Builds the golden-record vendor master (FR8) from every resolved MATCH
pair (auto-merge + LLM-confirmed + human-approved). A vendor's golden record
is one connected component of its match graph — if A matches B and B matches
C, all three become one golden vendor even if A and C were never directly
compared.

Rebuilt from scratch on every run rather than patched incrementally: with
~5,000 records this is instant, and a full recompute can never drift from an
inconsistent partial-update state — consistent with the project's batch
architecture (see docs/charter.md §9.2)."""

from dataclasses import dataclass

from concord.matching.schema import VendorRecordView

_CANONICAL_FIELDS = (
    "legal_name",
    "address_line1",
    "city",
    "state",
    "postal_code",
    "country",
    "tax_id",
    "phone",
    "category",
)


class _UnionFind:
    def __init__(self, ids: list[str]):
        self._parent = {i: i for i in ids}

    def find(self, i: str) -> str:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]  # path compression
            i = self._parent[i]
        return i

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


@dataclass
class GoldenVendorBuild:
    member_ids: list[str]
    canonical_fields: dict[str, str | None]


def _choose_representative(members: list[VendorRecordView]) -> VendorRecordView:
    """Picks the member record with the most non-null canonical fields —
    a simple, explainable "most complete wins" heuristic. Ties broken by
    (source, source_record_id) for determinism across rebuilds."""

    def completeness(record: VendorRecordView) -> int:
        return sum(1 for f in _CANONICAL_FIELDS if getattr(record, f))

    return max(
        members, key=lambda r: (completeness(r), r.source, r.source_record_id), default=members[0]
    )


def build_golden_vendors(
    records: list[VendorRecordView], match_pairs: set[tuple[str, str]]
) -> list[GoldenVendorBuild]:
    by_id = {r.id: r for r in records}
    uf = _UnionFind([r.id for r in records])

    for id_a, id_b in match_pairs:
        if id_a in by_id and id_b in by_id:
            uf.union(id_a, id_b)

    clusters: dict[str, list[str]] = {}
    for record_id in by_id:
        root = uf.find(record_id)
        clusters.setdefault(root, []).append(record_id)

    builds = []
    for member_ids in clusters.values():
        members = [by_id[mid] for mid in member_ids]
        representative = _choose_representative(members)
        canonical_fields = {f: getattr(representative, f) for f in _CANONICAL_FIELDS}
        builds.append(GoldenVendorBuild(member_ids=member_ids, canonical_fields=canonical_fields))

    return builds
