"""Evaluate LLM adjudications against the M1 ground truth.

Reports, for the pairs that were actually adjudicated:
  - How many were CONFIRMED_MATCH / CONFIRMED_NON_MATCH / UNCERTAIN
  - Precision/recall of CONFIRMED_MATCH against true duplicates
  - How many CONFIRMED_NON_MATCH were actually true duplicates (a real
    error the human reviewer in M5 would need to catch)

Usage:
    uv run python scripts/evaluate_adjudication.py
"""

import csv
from pathlib import Path

from sqlalchemy import select

from concord.db.models import LlmAdjudication, NormalizedVendorRecord
from concord.db.session import get_session

DATA_DIR = Path("data/synthetic")


def _load_ground_truth_pairs() -> set[frozenset[tuple[str, str]]]:
    pairs = set()
    with (DATA_DIR / "ground_truth_pairs.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pairs.add(
                frozenset(
                    {
                        (row["source_1"], row["record_id_1"]),
                        (row["source_2"], row["record_id_2"]),
                    }
                )
            )
    return pairs


def main() -> None:
    true_pairs = _load_ground_truth_pairs()

    session = next(get_session())
    try:
        adjudications = session.execute(select(LlmAdjudication)).scalars().all()
        if not adjudications:
            print("No adjudications found — run scripts/run_llm_adjudication.py first.")
            return

        id_to_natural_key = {
            row.id: (row.source, row.source_record_id)
            for row in session.execute(select(NormalizedVendorRecord)).scalars().all()
        }
    finally:
        session.close()

    counts = {"confirmed_match": 0, "confirmed_non_match": 0, "uncertain": 0}
    confirmed_match_true_positives = 0
    confirmed_non_match_errors = []

    for adjudication in adjudications:
        pair = frozenset(
            {
                id_to_natural_key[adjudication.record_id_1],
                id_to_natural_key[adjudication.record_id_2],
            }
        )
        is_true_duplicate = pair in true_pairs
        counts[adjudication.outcome] += 1

        if adjudication.outcome == "confirmed_match" and is_true_duplicate:
            confirmed_match_true_positives += 1
        if adjudication.outcome == "confirmed_non_match" and is_true_duplicate:
            confirmed_non_match_errors.append(pair)

    total = len(adjudications)
    confirmed_match_count = counts["confirmed_match"]
    precision = (
        confirmed_match_true_positives / confirmed_match_count if confirmed_match_count else 0.0
    )

    print(f"Total pairs adjudicated: {total}")
    print(f"  confirmed_match:     {counts['confirmed_match']}")
    print(f"  confirmed_non_match: {counts['confirmed_non_match']}")
    print(f"  uncertain:           {counts['uncertain']}  (routed to human review in M5)")
    print()
    print(f"confirmed_match precision (vs. ground truth): {precision:.3f}")
    print(
        f"confirmed_non_match errors (true duplicates wrongly rejected): "
        f"{len(confirmed_non_match_errors)}"
    )
    for pair in confirmed_non_match_errors[:10]:
        print(f"  {tuple(pair)}")


if __name__ == "__main__":
    main()
