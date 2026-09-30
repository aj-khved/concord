# Concord — Vendor Data Reconciliation & Risk Platform

A portfolio project: ingests vendor data from multiple messy, synthetic sources, reconciles duplicate vendor records using a deterministic-matching + LLM-adjudication hybrid, routes ambiguous cases to a human review queue, and surfaces a vendor risk signal (deterministic score + LLM-generated plain-English summary).

**Live demo:** https://concord-app.calmsmoke-3b88f840.westus2.azurecontainerapps.io
_(The database may be stopped between demos to control cost — see [PROJECT_STATUS.md](PROJECT_STATUS.md) if the demo appears down.)_

- Project charter, requirements, and architecture decisions: [docs/charter.md](docs/charter.md)
- Live status tracker: [PROJECT_STATUS.md](PROJECT_STATUS.md)
- Synthetic data design and messiness spec: [docs/data_messiness_spec.md](docs/data_messiness_spec.md)

Built using Claude Code as an AI development partner — architecture decisions, tradeoffs, and code review are documented throughout, not just the finished output.

_Status: M0–M8 complete (deployed to Azure Container Apps). M9 (documentation + portfolio case study) in progress._
