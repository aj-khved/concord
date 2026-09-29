# Project Status — Concord

Living tracker. Update this at the end of every milestone/session.

## Completed
- Project concept selected: Vendor Data Reconciliation & Risk Platform (see [docs/charter.md](docs/charter.md)).
- Charter written: problem statement, requirements, NFRs, success metrics, risks, architecture decisions, roadmap.
- Key decisions made: PostgreSQL, batch/ELT, deterministic+LLM-hybrid matching, FastAPI backend, server-rendered MVP UI, Azure for deployment.
- **M0: Project setup** — `uv`-managed Python project (`src/concord` package layout: ingestion, normalization, matching, risk, api, db), `ruff` (lint+format) and `pytest` configured and passing, `docker-compose.yml` for local Postgres, `.env.example`, GitHub Actions CI skeleton (lint + format-check + test).
- **M1: Synthetic data generation** — `scripts/generate_synthetic_data.py` produces 3 heterogeneous sources (ERP CSV, manual-upload CSV, partner JSON feed) with engineered messiness (legal-suffix drift, case drift, typos, address format variation, tax-ID format/omission, phone format variation) and 60 deliberately confusable non-duplicate pairs. Ground truth (`record_index.csv`, `ground_truth_pairs.csv`) generated and committed. Documented in [docs/data_messiness_spec.md](docs/data_messiness_spec.md). Default run: 3,060 vendors, ~1,640 records/source, 2,341 true duplicate pairs. 4 tests passing.
- **M2: Ingestion + normalization pipeline** — SQLAlchemy models + Alembic migrations for `raw_vendor_records` (append-only JSONB audit log), `normalized_vendor_records` (canonical schema, upserted on `(source, source_record_id)`), and `data_quality_runs`. Per-source readers (`concord/ingestion/readers.py`) and mappers (`concord/normalization/mappers.py`) undo each source's messiness into the canonical schema (FR1/FR2). Data-quality checks (`concord/normalization/quality.py`) implement FR11. Orchestrated by `concord/pipeline.py` (`scripts/run_ingestion.py` to run it). Verified against the real dataset: 4,921 records ingested across 3 sources, 0 data-quality failures, and idempotency confirmed empirically (raw table grows on re-run, normalized table does not — 3 runs → 14,763 raw rows, steady 4,921 normalized rows). Caught and fixed a real bug during manual verification: Source C's `+1 xxx xxx xxxx` phone format was retaining the country-code digit, causing 100% false `invalid_phone_length` failures — fixed via a dedicated `normalize_phone()`. 19 tests passing (including a DB integration test against a dedicated, throwaway `concord_test` database). CI now runs a Postgres service and applies migrations before tests.

## Current Work
- M3: Deterministic matching engine v1 — not yet started.

## Upcoming
- M4: LLM adjudication for borderline matches.
- M5: Review workflow + minimal UI.
- M6: Risk module.
- M7: API polish + observability.
- M8: Deploy to Azure.
- M9: Documentation + portfolio case study.

## Known Bugs
_None yet — pre-implementation._

## Technical Debt
_None yet._

## Architecture Decisions
See [docs/charter.md](docs/charter.md) §9 for the initial decision set. Future decisions (e.g., migration tool choice, blocking key design, LLM provider/model choice) will be logged here as they're made, with rationale.

## Risks
See [docs/charter.md](docs/charter.md) §8.

## Open Questions
- Exact synthetic "messiness" patterns to engineer into source data (to be defined in M1).
- Which LLM model to use for adjudication/risk summaries, and how to bound cost per run (to be defined in M4).
- Specific Azure services/tier for deployment (Flexible Server vs. Container Apps vs. App Service) — to be finalized at M8.

## Future Improvements
- React frontend upgrade (stretch M10).
- Real external risk-signal integration (news/filings APIs).
- Incremental/near-real-time ingestion.
