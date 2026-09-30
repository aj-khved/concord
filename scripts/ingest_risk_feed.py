"""Ingest data/synthetic/risk_feed.csv into vendor_risk_profiles (FR9).

Every risk-feed row is upserted by tax_id regardless of whether it currently
matches a golden vendor — a real risk feed doesn't know about our internal
reconciliation, so an "unmatched" row (no golden vendor currently has that
tax_id) is an expected, ordinary outcome, reported here for visibility.

Usage:
    uv run python scripts/ingest_risk_feed.py
"""

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from concord.db.models import GoldenVendor, VendorRiskProfile
from concord.db.session import get_session
from concord.observability.pipeline_run import track_pipeline_run
from concord.risk.join import GoldenVendorLike, RiskFeedRow, join_risk_feed_to_golden_vendors
from concord.risk.scoring import compute_risk

RISK_FEED_PATH = Path("data/synthetic/risk_feed.csv")


def _read_risk_feed(path: Path) -> list[RiskFeedRow]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            RiskFeedRow(
                tax_id=row["tax_id"],
                legal_name=row["legal_name"],
                sanctions_flag=row["sanctions_flag"] == "True",
                country_risk_tier=row["country_risk_tier"],
                financial_stability_score=int(row["financial_stability_score"]),
                notes=row["notes"],
            )
            for row in csv.DictReader(f)
        ]


if __name__ == "__main__":
    risk_rows = _read_risk_feed(RISK_FEED_PATH)

    session = next(get_session())
    try:
        with track_pipeline_run(session, "risk_ingestion") as run:
            golden_vendors = [
                GoldenVendorLike(id=str(v.id), tax_id=v.tax_id)
                for v in session.execute(select(GoldenVendor)).scalars().all()
            ]
            join_result = join_risk_feed_to_golden_vendors(risk_rows, golden_vendors)

            for row in risk_rows:
                assessment = compute_risk(
                    row.sanctions_flag, row.country_risk_tier, row.financial_stability_score
                )
                stmt = insert(VendorRiskProfile).values(
                    tax_id=row.tax_id,
                    legal_name=row.legal_name,
                    sanctions_flag=row.sanctions_flag,
                    country_risk_tier=row.country_risk_tier,
                    financial_stability_score=row.financial_stability_score,
                    risk_score=assessment.risk_score,
                    risk_level=assessment.risk_level,
                    notes=row.notes,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["tax_id"],
                    set_={
                        "legal_name": stmt.excluded.legal_name,
                        "sanctions_flag": stmt.excluded.sanctions_flag,
                        "country_risk_tier": stmt.excluded.country_risk_tier,
                        "financial_stability_score": stmt.excluded.financial_stability_score,
                        "risk_score": stmt.excluded.risk_score,
                        "risk_level": stmt.excluded.risk_level,
                        "notes": stmt.excluded.notes,
                    },
                )
                session.execute(stmt)

            session.commit()

            unmatched_count = len(join_result.unmatched_tax_ids)
            run.summary = {
                "rows_ingested": len(risk_rows),
                "matched_to_golden_vendor": len(join_result.matched),
                "unmatched": unmatched_count,
            }
    finally:
        session.close()

    print(f"Risk feed rows ingested: {len(risk_rows)}")
    print(f"Currently matched to a golden vendor: {len(join_result.matched)}")
    print(f"Currently unmatched (no golden vendor has this tax_id yet): {unmatched_count}")
