"""Run the M2 ingestion + normalization pipeline against data/synthetic.

Usage:
    uv run python scripts/run_ingestion.py
"""

import json
from pathlib import Path

from concord.db.session import get_engine, get_session
from concord.observability.pipeline_run import track_pipeline_run
from concord.pipeline import run_ingestion

if __name__ == "__main__":
    get_engine()  # fail fast with a clear error if the DB isn't reachable
    session = next(get_session())
    try:
        with track_pipeline_run(session, "ingestion") as run:
            summary = run_ingestion(Path("data/synthetic"), session)
            run.summary = {
                "batch_id": str(summary.batch_id),
                "per_source": summary.per_source,
            }
    finally:
        session.close()

    print(f"Batch: {summary.batch_id}")
    print(json.dumps(summary.per_source, indent=2))
