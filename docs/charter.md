# Project Charter — Concord: Vendor Data Reconciliation & Risk Platform

## 1. Problem Statement
Organizations source vendor/supplier data from multiple disconnected systems — ERP exports, manual spreadsheet uploads, legacy fixed-width extracts, partner APIs. The same real-world vendor ends up represented as multiple inconsistent records (name variants, formatting differences, stale addresses), causing duplicate payments, compliance blind spots, and inaccurate spend/risk reporting. Resolving this manually does not scale.

Concord ingests vendor data from multiple messy sources, reconciles duplicate/related records into a single "golden record" per vendor with a defensible confidence score, routes ambiguous cases to a human reviewer, and surfaces lightweight risk signals per vendor.

## 2. Target Users (personas — no real customers; built as a portfolio system)
- **Procurement/Vendor Master data steward** — reviews ambiguous match decisions, needs clear evidence and an audit trail.
- **AP/Procurement ops analyst** — needs a trustworthy, deduplicated vendor list to avoid duplicate payments.
- **Risk/compliance analyst** — wants a quick, explainable risk signal per vendor.

## 3. Goals
- Ingest 3+ structurally different synthetic vendor data sources into a canonical schema.
- Automatically resolve the majority of duplicate vendor records with measurable precision/recall against a labeled validation set.
- Route only genuinely ambiguous cases to a human reviewer, with clear evidence for the decision.
- Produce an explainable, lightweight vendor risk signal.
- Deploy a working, demoable system with observability into pipeline health.

## 4. Non-Goals (explicitly out of scope for v1)
- Real-time/streaming ingestion (batch is sufficient and appropriate — see architecture doc).
- Processing real client/production vendor data (synthetic data only).
- Automated financial risk prediction from real market data (risk scoring uses synthetic structured attributes + LLM narrative summary only).
- Multi-tenant / auth-heavy SaaS features (single-operator portfolio system).

## 5. Functional Requirements
| ID | Requirement |
|----|-------------|
| FR1 | Ingest vendor records from 3 heterogeneous synthetic sources (CSV format A, CSV format B, JSON feed) into raw staging tables, tracking source, batch, and load timestamp. |
| FR2 | Normalize each source into a canonical vendor schema (name, address, tax ID, phone, category, country) with a documented field mapping per source. |
| FR3 | Generate duplicate-candidate pairs using blocking keys (not naive all-pairs comparison). |
| FR4 | Score candidate pairs with deterministic similarity features (string, token, phonetic). |
| FR5 | For borderline-confidence pairs only, invoke an LLM adjudicator that returns a structured (schema-validated) judgment + rationale, under a per-run call/cost cap. |
| FR6 | Persist match decisions into three tiers: auto-merge (high confidence), auto-reject (low confidence), pending review (medium/borderline). |
| FR7 | Provide a review queue UI showing side-by-side evidence for pending pairs; reviewer can approve/reject/merge. Reviewer decisions are stored as labeled ground truth for future evaluation. |
| FR8 | Maintain a "golden record" vendor master table reflecting the current state of all merge decisions. |
| FR9 | Compute a vendor risk indicator from structured synthetic attributes (e.g., sanctions-list flag, country risk tier, financial-stability flag) plus an optional LLM-generated plain-English summary from an unstructured "notes" field. |
| FR10 | Expose a REST API: list/search vendors, get vendor detail + match history, list pending reviews, submit a review decision, trigger a pipeline run. |
| FR11 | Run data-quality checks on every ingestion (required fields present, valid formats, referential sanity) and produce a per-run report. |

## 6. Non-Functional Requirements
- **Reliability:** Pipeline runs are idempotent — re-running on the same input must not create duplicate staging/master records.
- **Performance:** Handle ~50,000–100,000 synthetic vendor records per full run in a few minutes on modest hardware.
- **Security:** No real PII/financial data anywhere in the repo or datasets. Secrets via environment variables (never committed). Input validation at all API boundaries. Explicit handling of prompt-injection risk from free-text fields fed to the LLM (the LLM never receives instructions to take action — only to classify/summarize, and its output is schema-validated before use).
- **Observability:** Structured logs; per-run metrics persisted (records processed, match tier counts, LLM calls + estimated cost, run duration, data-quality pass rate).
- **Maintainability:** Typed Python (Pydantic models), automated tests for matching logic and pipeline stages, linting/formatting enforced in CI.
- **Cost:** LLM usage capped and restricted to the borderline band only; cloud hosting kept on free/low-cost tiers during development, torn down when not actively being demoed.

## 7. Success Metrics
| Metric | Target |
|---|---|
| Matching precision (vs. labeled validation set) | ≥ 0.90 |
| Matching recall (vs. labeled validation set) | ≥ 0.85 |
| % of candidate pairs auto-resolved (not sent to review) | Majority, with review queue kept to a manageable size |
| Data-quality check pass rate per ingestion run | Tracked and trending toward 100% on clean batches |
| Full pipeline run duration (100k records) | Documented baseline, then improved release over release |
| LLM cost per 1,000 adjudicated pairs | Measured and reported (proves cost-awareness) |

## 8. Technical Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Synthetic data isn't messy/realistic enough to be a meaningful test | Deliberately engineer specific messiness patterns (abbreviations, legal-suffix variants, transpositions, address format drift) and document them as a "data messiness spec." |
| Naive all-pairs comparison is O(n²) | Blocking keys (e.g., normalized name prefix, postal code, tax ID fragment) generate only plausible candidate pairs. |
| LLM cost blowup / non-determinism | Route only the borderline confidence band to the LLM; structured JSON-schema output; per-run cost cap; cache repeated calls. |
| Scope creep across ingestion / matching / review UI / risk module | Strict milestone sequencing (see roadmap); MVP UI is server-rendered, not a full SPA. |
| Azure deployment cost/complexity creep | Use free/burstable tiers; provision infra only after the core logic is proven locally; document teardown steps. |

## 9. Key Architecture Decisions (see docs for full rationale as we build)
1. **PostgreSQL (relational), not NoSQL** — the data is structured with real relationships (source record → match group → golden record → review decision) and needs transactional integrity on merge/review actions. NoSQL would suit siloed, schema-variable documents without relationships — not this problem.
2. **Batch/ELT, not streaming** — vendor master updates are not sub-second real-time; a scheduled/on-demand batch pipeline matches the real-world pattern and keeps focus on the actual hard problem (entity resolution) rather than streaming infrastructure.
3. **Land-then-transform (ELT)** — raw source data is staged as-is first (preserves source fidelity and auditability), then transformed into the canonical schema in a separate, testable step.
4. **Deterministic scoring + LLM only for the borderline band** — pure LLM-for-every-pair doesn't scale in cost/latency and is hard to audit; pure deterministic string matching misses semantic equivalences (e.g., "Intl" vs. "International", legal-entity suffixes). Blocking → deterministic scoring → LLM adjudication only for the ambiguous middle band, with schema-validated structured output, is the defensible middle path.
5. **FastAPI (Python) backend** — matches existing Python/SQL fluency, strong typing via Pydantic, automatic OpenAPI docs (a legible artifact for interviews).
6. **MVP UI: server-rendered (Jinja2/HTMX), not a React SPA** — proves the matching engine and review workflow before investing in frontend architecture. A React frontend is a planned later milestone, not a cut feature.
7. **Deployment: Azure** — Azure Database for PostgreSQL (Flexible Server, burstable tier) + containerized FastAPI app on Azure App Service or Container Apps; secrets in App Service settings / Key Vault, never in code; GitHub Actions for CI and CD.

## 10. Repository Structure (initial)
```
concord/
  README.md
  PROJECT_STATUS.md
  docs/
    charter.md
    architecture.md        (decision log, grows over time)
  src/concord/
    ingestion/
    normalization/
    matching/
    risk/
    api/
    db/
    config.py
  tests/
  data/synthetic/
  scripts/
  .env.example
  pyproject.toml
  Dockerfile
  .github/workflows/ci.yml
  .gitignore
```

## 11. Development Roadmap
- **M0 — Project setup:** repo scaffold, tooling (venv/uv, ruff, pytest, pre-commit), local Postgres via Docker, CI skeleton.
- **M1 — Synthetic data generation:** generators for 3 messy source datasets + a hand-labeled ground-truth duplicate-pairs set for evaluation.
- **M2 — Ingestion + normalization:** raw staging tables, canonical schema mapping, data-quality checks/report.
- **M3 — Matching engine v1 (deterministic):** blocking + similarity scoring + confidence tiers; baseline precision/recall.
- **M4 — LLM adjudication:** structured output for the borderline band; cost caps; measure precision/recall improvement over v1.
- **M5 — Review workflow + minimal UI:** pending-review queue, approve/reject/merge, golden record table, feedback loop into future evaluation.
- **M6 — Risk module:** structured risk scoring + LLM risk-summary generation with documented failure modes.
- **M7 — API polish + observability:** full REST API, structured logging, per-run metrics, basic metrics endpoint/dashboard.
- **M8 — Deployment to Azure:** containerize, provision minimal resources, CI/CD, live smoke test.
- **M9 — Documentation + portfolio case study:** architecture diagrams, decision log, README, case study, interview talking points.
- **(Stretch) M10:** React frontend upgrade, real external risk-signal integration, incremental/near-real-time ingestion.
