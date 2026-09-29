"""Run the M2 ingestion + normalization pipeline against data/synthetic.

Usage:
    uv run python scripts/run_ingestion.py
"""

import json
from pathlib import Path

from concord.db.session import get_engine, get_session
from concord.pipeline import run_ingestion

if __name__ == "__main__":
    get_engine()  # fail fast with a clear error if the DB isn't reachable
    session = next(get_session())
    try:
        summary = run_ingestion(Path("data/synthetic"), session)
    finally:
        session.close()

    print(f"Batch: {summary.batch_id}")
    print(json.dumps(summary.per_source, indent=2))
