"""Rebuild the golden-vendor master table (FR8) from the current match
decisions (auto-merge, LLM-confirmed, human-approved).

Usage:
    uv run python scripts/build_golden_vendors.py
"""

from concord.db.session import get_session
from concord.golden.rebuild import rebuild_golden_vendors

if __name__ == "__main__":
    session = next(get_session())
    try:
        summary = rebuild_golden_vendors(session)
    finally:
        session.close()

    print(f"Golden vendors: {summary.golden_vendor_count}")
    print(f"Source records: {summary.record_count}")
    print(f"Largest cluster: {summary.largest_cluster_size} member records")
