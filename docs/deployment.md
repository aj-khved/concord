# Deployment (M8)

## Architecture

| Component | Service | Why |
|---|---|---|
| App runtime | Azure Container Apps (`concord-app` in `concord-env`) | Scales to zero when idle — near-$0 compute cost between demos. Azure App Service's cheapest container-capable tier runs continuously (~$13/month) regardless of traffic; Container Apps only bills while a request is actually being handled (plus a small always-on minimum, which we've set to 0 min replicas). |
| Database | Azure Database for PostgreSQL Flexible Server, Burstable B1ms (`concord-db-ajk2026`) | Matches the charter's decision. No true serverless/scale-to-zero option exists for Azure Postgres, so this is the one component with a real ongoing cost if left running (~$12–15/month) — see **Cost management** below. |
| Container registry | GitHub Container Registry (`ghcr.io/aj-khved/concord`) | Free, and ties the image directly to the GitHub repo. Azure Container Registry's Basic tier costs ~$5/month for capability this project doesn't need. |
| Secrets | Container App secrets (`database-url`, `anthropic-key`) | Never baked into the image or committed to the repo — injected as env vars from Azure's secret store at container start. |
| CI | GitHub Actions (`.github/workflows/ci.yml`) | Lint, format-check, migrate, test — against a real Postgres service container. |
| CD | GitHub Actions (`.github/workflows/deploy.yml`) | Triggered by `workflow_run` on CI's successful completion (never deploys a commit that failed tests) — builds the image, pushes to GHCR, updates the Container App to the new image tag. |

## Resource inventory

- Resource group: `concord-rg`
- Postgres Flexible Server: `concord-db-ajk2026` (region: **Central US**)
- Container Apps environment: `concord-env` (region: **West US 2**)
- Container App: `concord-app`
- Live URL: https://concord-app.calmsmoke-3b88f840.westus2.azurecontainerapps.io

**Why two different regions:** `East US` and `East US 2` were restricted for this (new) subscription's Postgres Flexible Server SKU. `Central US` worked for Postgres but hit an `AKSCapacityHeavyUsage` error for Container Apps at the time of provisioning. `West US 2` worked for Container Apps. Cross-region traffic between the app and database adds a small amount of latency but no functional issue — worth revisiting if this were a real production deployment with stricter latency requirements.

## Cost management — stopping the database between demos

Postgres Flexible Server is the only component that costs money while idle. Stop it when not actively demoing:

```bash
az postgres flexible-server stop --resource-group concord-rg --name concord-db-ajk2026
```

Start it again before a demo (takes ~1–2 minutes to become available):

```bash
az postgres flexible-server start --resource-group concord-rg --name concord-db-ajk2026
```

A stopped server auto-resumes after 7 days regardless (Azure's limit), so worst case it silently starts billing again after a week — check `az postgres flexible-server show` if it's been a while.

While the database is stopped, the app itself will still scale down to zero replicas naturally (Container Apps has no traffic to serve) but will return connection errors if something tries to hit it, since the DB is unreachable. That's expected — this is a demo project, not a production SLA.

## Manual redeploy (if needed outside the CI/CD pipeline)

```bash
docker build -t ghcr.io/aj-khved/concord:latest .
docker push ghcr.io/aj-khved/concord:latest
az containerapp update --name concord-app --resource-group concord-rg --image ghcr.io/aj-khved/concord:latest
```

## Seeding data

The deployed database was seeded by running the same local pipeline scripts (`run_ingestion.py`, `run_matching.py`, `run_llm_adjudication.py`, `build_golden_vendors.py`, `ingest_risk_feed.py`, `run_risk_summarization.py`) against it directly, with `DATABASE_URL` pointed at the Azure Postgres connection string instead of the local Docker one. This reused the exact same, already-verified pipeline rather than building any separate "production seeding" mechanism — the batch architecture (see charter §9.2) made this trivial.
