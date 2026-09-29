# Project Status — Concord

Living tracker. Update this at the end of every milestone/session.

## Completed
- Project concept selected: Vendor Data Reconciliation & Risk Platform (see [docs/charter.md](docs/charter.md)).
- Charter written: problem statement, requirements, NFRs, success metrics, risks, architecture decisions, roadmap.
- Key decisions made: PostgreSQL, batch/ELT, deterministic+LLM-hybrid matching, FastAPI backend, server-rendered MVP UI, Azure for deployment.

## Current Work
- M0: Project setup (repo scaffold, tooling, local Postgres, CI skeleton) — not yet started.

## Upcoming
- M1: Synthetic data generation + labeled ground truth.
- M2: Ingestion + normalization pipeline.
- M3: Deterministic matching engine v1.
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
