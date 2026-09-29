"""Read each source's raw file into a uniform (source, source_record_id, payload)
shape, without interpreting or cleaning any field values — that's the
normalization layer's job (concord.normalization.mappers)."""

import csv
import json
from pathlib import Path
from typing import NamedTuple


class RawRecord(NamedTuple):
    source: str
    source_record_id: str
    payload: dict


def read_source_a(path: Path) -> list[RawRecord]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [RawRecord("A", row["vendor_id_src"], row) for row in rows]


def read_source_b(path: Path) -> list[RawRecord]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Source B has no natural ID column in the raw file itself — the manual
    # upload format never had one. We assign one at read time from row order,
    # which is stable as long as the file isn't re-ordered between runs.
    return [RawRecord("B", f"B-{i + 1:06d}", row) for i, row in enumerate(rows)]


def read_source_c(path: Path) -> list[RawRecord]:
    records = json.loads(path.read_text(encoding="utf-8"))
    return [RawRecord("C", rec["recordId"], rec) for rec in records]


READERS = {"A": read_source_a, "B": read_source_b, "C": read_source_c}
