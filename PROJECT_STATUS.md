# Project Status — Concord

Living tracker. Update this at the end of every milestone/session.

## Completed
- Project concept selected: Vendor Data Reconciliation & Risk Platform (see [docs/charter.md](docs/charter.md)).
- Charter written: problem statement, requirements, NFRs, success metrics, risks, architecture decisions, roadmap.
- Key decisions made: PostgreSQL, batch/ELT, deterministic+LLM-hybrid matching, FastAPI backend, server-rendered MVP UI, Azure for deployment.
- **M0: Project setup** — `uv`-managed Python project (`src/concord` package layout: ingestion, normalization, matching, risk, api, db), `ruff` (lint+format) and `pytest` configured and passing, `docker-compose.yml` for local Postgres, `.env.example`, GitHub Actions CI skeleton (lint + format-check + test).
- **M1: Synthetic data generation** — `scripts/generate_synthetic_data.py` produces 3 heterogeneous sources (ERP CSV, manual-upload CSV, partner JSON feed) with engineered messiness (legal-suffix drift, case drift, typos, address format variation, tax-ID format/omission, phone format variation) and 60 deliberately confusable non-duplicate pairs. Ground truth (`record_index.csv`, `ground_truth_pairs.csv`) generated and committed. Documented in [docs/data_messiness_spec.md](docs/data_messiness_spec.md). Default run: 3,060 vendors, ~1,640 records/source, 2,341 true duplicate pairs. 4 tests passing.
- **M2: Ingestion + normalization pipeline** — SQLAlchemy models + Alembic migrations for `raw_vendor_records` (append-only JSONB audit log), `normalized_vendor_records` (canonical schema, upserted on `(source, source_record_id)`), and `data_quality_runs`. Per-source readers (`concord/ingestion/readers.py`) and mappers (`concord/normalization/mappers.py`) undo each source's messiness into the canonical schema (FR1/FR2). Data-quality checks (`concord/normalization/quality.py`) implement FR11. Orchestrated by `concord/pipeline.py` (`scripts/run_ingestion.py` to run it). Verified against the real dataset: 4,921 records ingested across 3 sources, 0 data-quality failures, and idempotency confirmed empirically (raw table grows on re-run, normalized table does not — 3 runs → 14,763 raw rows, steady 4,921 normalized rows). Caught and fixed a real bug during manual verification: Source C's `+1 xxx xxx xxxx` phone format was retaining the country-code digit, causing 100% false `invalid_phone_length` failures — fixed via a dedicated `normalize_phone()`. 19 tests passing (including a DB integration test against a dedicated, throwaway `concord_test` database). CI now runs a Postgres service and applies migrations before tests.
- **M3: Deterministic matching engine v1** — blocking (`concord/matching/blocking.py`, postal-code + name-prefix/city keys), similarity scoring (`concord/matching/scoring.py`, weighted average over available features only — name via rapidfuzz, exact-match postal/phone/tax-ID/category, missing fields excluded rather than penalized), and confidence tiering (`concord/matching/engine.py`: auto-merge ≥0.90, auto-reject ≤0.55, pending-review between). Persisted to a new `match_candidates` table. `scripts/run_matching.py` runs it; `scripts/evaluate_matching.py` scores the result against the M1 ground truth. **Results on the real dataset: candidate recall 1.000, auto-merge precision 1.000 / recall 0.984 (exceeds the charter's ≥0.90/≥0.85 targets), 0/60 confusable hard-negative pairs wrongly auto-merged, and all 37 pending-review pairs were genuine true duplicates (0 false positives in the review queue).** Caught and fixed an evaluation-script bug along the way (hard-negative leakage check didn't compare `vendor_id`, so it flagged a vendor's own legitimate cross-source records as false positives — corrected, real leakage is 0). Honest caveat: this is a clean result on synthetic data we designed; real-world data will likely need threshold retuning. 14 new unit tests (47 total).

- **M4: LLM adjudication for borderline matches** — `concord/llm/adjudicator.py` calls Claude Haiku 4.5 with a forced tool call (`adjudicate_vendor_pair`, schema-validated JSON output — the model literally cannot return anything else), so its only possible actions are structured judgment fields, not free text or code — the key mitigation against prompt injection via ingested record data (system prompt also explicitly tells the model record fields are data, not instructions). Below a 0.70 confidence threshold, results are treated as `uncertain` regardless of the model's yes/no answer, and stay routed to human review (M5) rather than being auto-trusted. Persisted to a new `llm_adjudications` table (one adjudication per candidate, enforced by a unique constraint — idempotent and cost-safe to re-run). `scripts/run_llm_adjudication.py` runs it (capped at `LLM_MAX_CALLS_PER_RUN`, default 200); `scripts/evaluate_adjudication.py` scores it against ground truth. **Ran for real against a personal Anthropic API key** (blocked initially by North Highland's org-creation policy on the corporate domain — resolved by signing up with a personal account, appropriate since this is a personal project): all 37 pending-review pairs were correctly `confirmed_match` (precision 1.000, 0 errors) — combined with M3's 2,304 auto-merges, the full pipeline resolves all 2,341 ground-truth pairs with zero mistakes on this dataset. Hit and fixed two real API-compatibility issues along the way: this SDK/API generation replaced `temperature` with an `effort` parameter, and `effort` itself isn't supported on Haiku 4.5 specifically — removed it, relying on the model default. 6 new unit tests using a fake client (no real network calls in the test suite) (39 total). Honest caveat, same as M3: this is a clean result on synthetic data — real-world messiness and genuinely ambiguous cases would exercise the `uncertain` path much more.

- **M5: Review workflow + minimal UI** — `concord/review/resolution.py` is the single source of truth for a pair's final status (human decision > LLM adjudication > deterministic tier). `concord/golden/builder.py` implements union-find clustering over every MATCH-status pair into golden vendors (FR8), picking each cluster's most-complete member record as the canonical representative; `concord/golden/rebuild.py` orchestrates a full rebuild against the DB (cheap enough at ~5,000 records to run synchronously after every human decision). Server-rendered FastAPI + Jinja2 UI (`concord/api/app.py`): dashboard, review queue (side-by-side evidence, approve/reject), and a browsable vendor master. **Verified live in a browser**, not just via tests — and that's exactly how a real bug was caught: `match_candidates` is append-only (one batch per matching-engine run), and neither the dashboard nor the golden-vendor rebuild was filtering to the latest batch, so a stray second batch (from re-running `run_matching.py` during M3 verification) double-counted pairs. Fixed by filtering both to the most recent `batch_id`; added a regression test (`test_golden_rebuild_integration.py`) that fabricates two batches with conflicting tiers and asserts only the newer one is honored. Also fixed a Starlette API-signature change (`TemplateResponse` now takes `request` positionally, not inside the context dict) and a dark-background/dark-text contrast bug from not setting an explicit `color-scheme`/background. **Real result after fixes: 2,341 matches, 245 non-matches, 0 needing human review, 3,060 golden vendors from 4,921 source records** — exactly the true vendor count M1 generated. Manually exercised the full approve/reject flow end-to-end in the browser against a manufactured test pair (cleaned up afterward). 13 new unit/integration tests (52 total).

## Current Work
- M6: Risk module — not yet started.

## Upcoming
- M7: API polish + observability.
- M8: Deploy to Azure.
- M9: Documentation + portfolio case study.

## Known Bugs
_None currently open — see M5 entry above for bugs found and fixed this milestone._

## Technical Debt
- Dashboard and vendor-list queries (`concord/api/app.py`) load full result sets into Python and count/sort in-memory rather than using SQL `COUNT`/`GROUP BY`/pagination. Fine at ~5,000 records; would need addressing before this scaled to real production volumes.
- `golden_vendors` is rebuilt from scratch on every change rather than patched incrementally (deliberate simplicity choice, see `concord/golden/rebuild.py` docstring) — revisit only if rebuild time becomes noticeable at much larger scale.

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
