# TDO Platform — Claude Code Reference

## Project Overview

TDO (The Data Observatory) is a data catalogue platform that harvests, harmonises,
and makes searchable open datasets from five statistical portals: Eurostat, OECD,
Statistics Finland (StatFin), World Bank, and UN Data. A FastAPI backend indexes
~7 000 datasets with pgvector embeddings and full-text search; a React/Vite frontend
lets users search and browse results. The pipeline runs as Azure Container Apps Jobs
that fetch raw metadata, optionally harmonise it via an LLM, generate embeddings via
a Cohere serverless endpoint, and upsert records into PostgreSQL.

---

## Architecture

| Component | Azure resource name | Value |
|---|---|---|
| API container app | `tdo-app-api-dev` | `https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io` |
| Frontend static web app | `tdo-frontend-dev` | check `az staticwebapp show -n tdo-frontend-dev -g tdo-platform-dev --query properties.defaultHostname` |
| Container Apps Environment | `tdo-cae-dev` | northeurope |
| ACR registry | `tdoacrdev` | `tdoacrdev.azurecr.io` |
| GHCR repo (primary) | `ghcr.io/hesekielnavaia/tdo-api` | used by CI/CD deploy-app |
| PostgreSQL | `tdo-pg-dev.postgres.database.azure.com` | DB name: `tdo`, AAD auth only, private endpoint |
| Embedder endpoint | `tdo-embedder-dev` (Azure AI Foundry serverless) | `https://tdo-embedder-dev.swedencentral.models.ai.azure.com` |
| Embedder model | Cohere-embed-v3-multilingual | 1024-dim vectors |
| OpenAI (harmoniser fallback) | `tdo-openai-dev` | gpt-4o deployment, swedencentral |
| Key Vault | `tdo-kv-dev` | private endpoint only — not reachable from local machine |
| Storage account | `tdotdosadev` | private endpoint |
| Harvest job | `tdo-job-harvest-dev` | full harvest → harmonise → embed → index |
| Embed job | `tdo-job-embed-dev` | placeholder image (not yet wired to real image) |
| Harmonise job | `tdo-job-harmonise-dev` | placeholder image (not yet wired) |
| Resource group | `tdo-platform-dev` | subscription `2984fe6f-916e-4ab1-ba5d-c34cdf8f9dd8` |
| GitHub repo | `https://github.com/HesekielNavaia/tdo-platform` | branch: `main` |
| AI Hub (northeurope) | `tdo-ai-hub-dev` / project `tdo-ai-project-dev` | |
| AI Hub (swedencentral) | `tdo-ai-hub-sc-dev` / project `tdo-ai-project-sc-dev` | embedder lives here |

### Secret env vars on `tdo-app-api-dev`

These are stored as container-app secrets and referenced via `secretref:`:

| Env var | Secret name | Value |
|---|---|---|
| `TDO_API_KEYS` | `tdo-api-keys` | `tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963` |
| `EMBEDDING_ENDPOINT` | `embedder-endpoint` | `https://tdo-embedder-dev.swedencentral.models.ai.azure.com` |
| `EMBEDDING_API_KEY` | `embedder-key` | retrieve with `az ml serverless-endpoint get-credentials -n tdo-embedder-dev -g tdo-platform-dev -w tdo-ai-project-sc-dev` |

---

## Running the Platform Locally

```bash
# Start postgres, embeddings (HuggingFace TEI), ollama (Phi-4), MinIO, and API
docker compose up

# API runs at http://localhost:8000 with TDO_API_KEYS=dev-key-123
# First run: pull Phi-4 model into ollama
docker exec ollama ollama pull phi4

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
# Vite dev server at http://localhost:5173
```

The docker-compose uses:
- PostgreSQL with pgvector at `localhost:5432` (DB: `tdo_dev`)
- HuggingFace TEI at `localhost:8080` for embeddings (multilingual-e5-large)
- Ollama at `localhost:11434` for harmonisation (phi4)

---

## Deployment

### CI/CD workflows

| Workflow | File | Trigger | What it does |
|---|---|---|---|
| Deploy Application | `deploy-app.yml` | push to `main`, manual | Builds Docker image → pushes to GHCR + ACR → updates `tdo-app-api-dev` with new image + secrets → updates `tdo-job-harvest-dev` image → smoke test |
| Deploy Infrastructure | `deploy-infra.yml` | push to `main`, manual | Runs Bicep what-if then deploys infra |
| Self-Heal | `self-heal.yml` | schedule / webhook | Auto-fixes deployment drift |

**GitHub environment**: `dev` — holds secrets `TDO_API_KEYS`, `EMBEDDER_ENDPOINT`, `EMBEDDER_KEY` (required for the "Restore required secrets" workflow step).

### Manual deploy trigger

```bash
# Trigger deploy-app workflow via GitHub CLI
gh workflow run deploy-app.yml --ref main

# Or push any commit to main — the push event triggers it automatically
```

### Check which revision is live

```bash
az containerapp revision list \
  -n tdo-app-api-dev -g tdo-platform-dev \
  --query "[].{name:name,active:properties.active,traffic:properties.trafficWeight,created:properties.createdTime}" \
  -o table

# Check the git SHA of the active revision
az containerapp show -n tdo-app-api-dev -g tdo-platform-dev \
  --query "properties.template.containers[0].env[?name=='GIT_SHA'].value" -o tsv

# Or just hit the health endpoint
curl -s -H "X-API-Key: tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963" \
  https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io/v1/health \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('git:', d['git_sha'], 'embedder:', d['model_endpoints']['embedder'])"
```

---

## Azure CLI Gotchas

**Critical — read before running any deployment commands:**

1. **ACR uses 8-char SHA** — The CI/CD workflow uses `cut -c1-8` to get a SHORT_SHA for image tags. Always use `git rev-parse --short=8 HEAD` (not `--short` which defaults to 7 chars). Mismatch causes "image not found" errors.

2. **`az containerapp update --set-env-vars` replaces ALL env vars** — Despite the name, when used with `--image`, it overwrites the entire env var set with only what you specify. Always include every required env var (including secret refs) in the same `--set-env-vars` call. This is why CI/CD was repeatedly wiping `TDO_API_KEYS` and `EMBEDDING_ENDPOINT`.

3. **`az containerapp job update` does NOT support `--registry-server` or `--registry-identity` flags** — Use only `--image`. Registry credentials are configured separately at the container app job level.

4. **Container app actual name is `tdo-app-api-dev`** (with `-dev` suffix) — Not `tdo-app-api`. Always verify with `az containerapp list -g tdo-platform-dev`.

5. **ACR auth fails when set from local machine** — `az containerapp update --image tdoacrdev.azurecr.io/...` fails with UNAUTHORIZED unless registry credentials are pre-configured. Run this first:
   ```bash
   ACR_PASS=$(az acr credential show -n tdoacrdev -g tdo-platform-dev --query "passwords[0].value" -o tsv)
   az containerapp registry set -n tdo-app-api-dev -g tdo-platform-dev \
     --server tdoacrdev.azurecr.io --username tdoacrdev --password "$ACR_PASS"
   ```
   The CI/CD uses GHCR (`ghcr.io/hesekielnavaia/tdo-api`) not ACR directly — prefer that path.

6. **Key Vault is on private network** — `az keyvault secret list/set` from a local machine returns `ForbiddenByConnection`. Secrets must be set via the container app secret mechanism, not directly via KV CLI.

7. **PostgreSQL is not reachable from local machine** — The DB is behind a private endpoint. All DB queries must run inside the container app or via the API.

8. **`az ml serverless-endpoint` workspace name** — The embedder is in `tdo-ai-project-sc-dev` (swedencentral), NOT `tdo-ai-hub-dev-project` (which doesn't exist). The workspace name matters for `az ml` commands.

9. **Two Alembic heads after parallel migrations** — If two migration files share the same `down_revision`, Alembic throws `MultipleHeadsError` on `upgrade head`. Fix by creating a merge migration with `down_revision = ("rev_a", "rev_b")` as a tuple.

---

## Common Commands (copy-paste ready)

```bash
RG=tdo-platform-dev
APP=tdo-app-api-dev
BASE=https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io
KEY=tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963

# ── Revisions ───────────────────────────────────────────────────────────────

# Check which revision is live and its git SHA
az containerapp revision list -n $APP -g $RG \
  --query "[].{name:name,active:properties.active,traffic:properties.trafficWeight,created:properties.createdTime}" \
  -o table

# Force traffic to the latest revision
LATEST=$(az containerapp revision list -n $APP -g $RG --query "[0].name" -o tsv)
az containerapp ingress traffic set -n $APP -g $RG --revision-weight $LATEST=100

# Rollback to previous revision (list first, then pin)
az containerapp revision list -n $APP -g $RG -o table
az containerapp ingress traffic set -n $APP -g $RG --revision-weight <prev-revision-name>=100

# ── ACR images ──────────────────────────────────────────────────────────────

# List recent ACR image tags
az acr repository show-tags --name tdoacrdev --repository tdo-api \
  --top 10 --orderby time_desc

# Build and push to ACR manually (8-char SHA tag)
SHORT_SHA=$(git rev-parse --short=8 HEAD)
az acr build --registry tdoacrdev -g $RG \
  --image tdo-api:$SHORT_SHA --image tdo-api:latest --file Dockerfile .

# ── Jobs ────────────────────────────────────────────────────────────────────

# Run harvest job for a specific portal (statfin | eurostat | worldbank | oecd | undata)
az containerapp job start -n tdo-job-harvest-dev -g $RG \
  --image ghcr.io/hesekielnavaia/tdo-api:latest \
  --env-vars "PORTAL_ID=eurostat"

# Run backfill-embeddings for all records with NULL embedding_vec (via API)
curl -s -X POST "$BASE/v1/admin/backfill-embeddings" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"batch_size": 50, "max_records": 5000}'

# Run backfill for a single portal
curl -s -X POST "$BASE/v1/admin/backfill-embeddings" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"portal_id": "statfin", "batch_size": 50, "max_records": 2000}'

# ── DB record and embedding counts ──────────────────────────────────────────

# Record counts per portal (via API — no direct DB access from local)
curl -s "$BASE/v1/stats" -H "X-API-Key: $KEY"

# Health (includes per-portal record counts + embedder status)
curl -s "$BASE/v1/health" -H "X-API-Key: $KEY"

# ── Restore embedder secrets (manual fix after CI/CD wipe) ──────────────────

EMBEDDER_KEY=$(az ml serverless-endpoint get-credentials \
  -n tdo-embedder-dev -g $RG -w tdo-ai-project-sc-dev \
  --query primaryKey -o tsv)

az containerapp secret set -n $APP -g $RG \
  --secrets \
    "tdo-api-keys=tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963" \
    "embedder-endpoint=https://tdo-embedder-dev.swedencentral.models.ai.azure.com" \
    "embedder-key=$EMBEDDER_KEY"

az containerapp update -n $APP -g $RG \
  --set-env-vars \
    "TDO_API_KEYS=secretref:tdo-api-keys" \
    "EMBEDDING_ENDPOINT=secretref:embedder-endpoint" \
    "EMBEDDING_API_KEY=secretref:embedder-key"

# ── Exec/debug ───────────────────────────────────────────────────────────────

# There is no SSH/exec for Azure Container Apps — use logs instead
az containerapp logs show -n $APP -g $RG --follow --tail 50
```

---

## Database

**Type**: Azure Database for PostgreSQL Flexible Server with pgvector extension
**Server**: `tdo-pg-dev.postgres.database.azure.com`
**DB name**: `tdo`
**Auth**: Azure AD (Managed Identity) only — no password auth. Not reachable from local machine (private endpoint).
**Connection**: The API and jobs use `postgresql+asyncpg://` with a short-lived AAD token as password. Migrations use `psycopg2` via Alembic.

### Key tables

| Table | Purpose |
|---|---|
| `datasets` | Main searchable records (7 000+) |
| `dataset_versions` | Full MVM snapshot history per record |
| `dataset_aliases` | Maps old/changed source_ids to canonical UUIDs |
| `pipeline_runs` | Execution tracking per portal/stage |
| `metadata_review_queue` | Low-confidence records needing human review |

### Critical column details

**`embedding` vs `embedding_vec`**
- `embedding` (JSONB) — the raw float array stored as JSON by the indexer
- `embedding_vec` (vector(1024)) — the pgvector column used for cosine similarity search
- Migration 0005 added `embedding_vec` and did a one-time backfill from `embedding`
- New records inserted after 0005 had `embedding` populated but `embedding_vec = NULL`, making them invisible to semantic search
- **Fixed**: the indexer now writes `CAST(:embedding AS vector)` to `embedding_vec` on insert/update; migration 0014 backfills all existing NULL rows

**`portal_id` / `source_portal`** — exact string values in the DB:

| Portal | Value stored in DB |
|---|---|
| Statistics Finland | `statfin` |
| Eurostat | `eurostat` |
| OECD | `oecd` |
| World Bank | `worldbank` (NOT `world_bank`) |
| UN Data | `undata` (NOT `un_data`) |

**`source_id` format per portal**:

| Portal | Example source_id |
|---|---|
| StatFin | `StatFin/jyev/statfin_jyev_pxt_12sy.px` |
| Eurostat | `NAMQ_10_GDP` |
| OECD | `NAAG` (short form — SDMX agency adds `DF_` prefix) |
| World Bank | `38` (numeric source ID from WB API) |
| UN Data | `SP.POP.TOTL` or SDG indicator like `1.1.1` |

**FTS column**: `fts_doc` — generated tsvector column (STORED) from `title || description || publisher`. Used by the `websearch_to_tsquery` fallback in `/v1/query`.

**confidence_score**: records with `< 0.3` are filtered from all search results.

### Running migrations

```bash
# Migrations run automatically on API startup via _run_migrations() in lifespan
# To run manually (requires DB access from within the network):
python -m src.jobs.migrate   # uses managed identity — only works inside Azure
```

---

## Portal URL Formats

Exact working URL patterns stored in the `dataset_url` column:

| Portal | URL pattern | Example |
|---|---|---|
| **Eurostat** | `https://ec.europa.eu/eurostat/databrowser/explore/all/all_themes?lang=en&display=list&sort=category&extractionId={ID}` | `extractionId=NAMQ_10_GDP` |
| **OECD** | `https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=DF_{ID}&df[ag]={AGENCY}` | `df[id]=DF_QNA&df[ag]=OECD.SDD.NAD` |
| **StatFin** | `https://pxdata.stat.fi/PXWeb/pxweb/en/StatFin/StatFin__{folder}/{table}.px` | `StatFin__jyev/statfin_jyev_pxt_12sy.px` |
| **World Bank** | `https://databank.worldbank.org/source/{ID}` | `source/38` |
| **UN Data** | `https://unstats.un.org/sdgs/indicators/database/?indicator={ID}` | `indicator=1.1.1` |

Key fixes in git history:
- **StatFin**: PxWeb viewer requires uppercase `/PXWeb/` and `{db}__{folder}` double-underscore format — lowercase `/PxWeb/` or missing double-underscore returns HTTP 500
- **OECD**: `df[ag]` must be the real SDMX sub-directorate agency (e.g. `OECD.SDD.NAD`, `OECD.CFE.EDS`) — bare `OECD` causes "no data available". `df[id]` is the part after `@` in compound IDs (`DSD_NASU@DF_VALUATION_T1620` → `DF_VALUATION_T1620`). The adapter reads real agencyID from `sdmx.oecd.org/public/rest/dataflow/all/all/latest?detail=allstubs` — re-run harvest to fix any records with wrong agency.
- **World Bank**: must use `databank.worldbank.org/source/{id}` not `data.worldbank.org/source/{id}`
- **Eurostat**: must use `extractionId=` query param format, not `/databrowser/view/{id}` (old path gives generic explore page)

---

## API Endpoints

All endpoints require `X-API-Key: tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963` header.

```bash
BASE=https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io
KEY=tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963

# Health — git SHA, per-portal record counts, embedder/harmoniser status
curl -s "$BASE/v1/health" -H "X-API-Key: $KEY" | python3 -m json.tool

# Stats — total records and breakdown by portal/theme/geo/access_type
curl -s "$BASE/v1/stats" -H "X-API-Key: $KEY" | python3 -m json.tool

# Natural language search (POST only)
curl -s -X POST "$BASE/v1/query" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"GDP growth Europe","limit":10}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(r['portal'],'|',r['title'][:70]) for r in d['results']]"

# Structured dataset search (GET with query params)
# Params: q, portal, theme, geo, format, access_type, limit, offset, sort, order
curl -s "$BASE/v1/datasets?q=inflation&portal=eurostat&limit=5" \
  -H "X-API-Key: $KEY" | python3 -m json.tool

# List portals
curl -s "$BASE/v1/portals" -H "X-API-Key: $KEY" | python3 -m json.tool

# Backfill embedding_vec for records with NULL (admin — runs inline)
curl -s -X POST "$BASE/v1/admin/backfill-embeddings" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"batch_size": 50, "max_records": 5000}'
```

**Search behaviour**:
1. If `EMBEDDING_ENDPOINT` configured → cosine similarity on `embedding_vec`
2. Always runs FTS via `websearch_to_tsquery('english', word1 OR word2 OR ...)` (OR semantics)
3. Portal fill: ILIKE fallback per portal for any portal not yet in the result pool (runs even if FTS returns 0 results)
4. Results diversity: up to 2 per portal before filling remaining slots by score

---

## Known Issues and Fix History

| Commit | Issue | Fix |
|---|---|---|
| `0110838` | CI/CD wiped `TDO_API_KEYS` + `EMBEDDING_ENDPOINT` on every deploy (--set-env-vars replaces all env vars) | Added "Restore required secrets" step in `deploy-app.yml`; all secret refs now explicitly set in `--set-env-vars` |
| `0110838` | `embedding_vec` NULL for all newly indexed records (indexer only wrote JSONB `embedding`, not pgvector column) | Indexer now writes `embedding_vec = CAST(:embedding AS vector)`; migration 0014 backfills existing records |
| `0110838` | FTS returned 0 results for multi-word queries ("population age structure Finland") because `plainto_tsquery` requires ALL words (AND) | Switched to `websearch_to_tsquery` with "word1 OR word2 OR ..." for OR semantics |
| `0110838` | Portal fill (ILIKE fallback) skipped entirely when FTS returned 0 results | Removed `and results` guard — portal fill now always runs |
| `be38c0d` | StatFin URLs returned HTTP 500 | Fixed to uppercase `/PXWeb/` and `StatFin__{folder}` double-underscore path |
| `cc55727` | Eurostat URLs pointed to generic explore page | Fixed to `extractionId=` query param format |
| `9aa5f58` | `portal_id` stored as full URL strings instead of short names | Normalised to `statfin`, `eurostat`, `oecd`, `worldbank`, `undata` |
| `5ff67d0` | World Bank URLs used `data.worldbank.org` (returns wrong page) | Fixed to `databank.worldbank.org/source/{id}` |
| `2efc5f3` | OECD URLs used old SDMX endpoint | Fixed to `data-explorer.oecd.org/vis?df[id]=DF_{id}` |
| `97eaf4b` | UN Data had only 96 records (only one agency harvested) | Expanded adapter to all SDMX agencies + UN Stats SDG series (708 indicators) |
| `918dff7` | deploy-app used ACR image path; container app needed GHCR | Fixed workflow to use `ghcr.io/hesekielnavaia/tdo-api` |
| `fe15ae8` | Frontend `VITE_API_URL` was relative; failed when deployed | Hardcoded full API base URL as fallback |
| `b018c50` | ACR admin not enabled; CI/CD couldn't push images | Enabled ACR admin user; switched to admin credential login |
| `0854500` | Migration FTS column used `array_to_string` (STABLE, not IMMUTABLE) in GENERATED column | Removed array fields from fts_doc; uses only title + description + publisher |

---

## What NOT To Do

- **Never assume the container app name** — always verify with `az containerapp list -g tdo-platform-dev`. The actual name is `tdo-app-api-dev` (not `tdo-app-api`).
- **Never use 7-char SHA with ACR** — CI/CD tags are 8-char. Use `git rev-parse --short=8 HEAD`. 7-char tags don't exist in ACR and cause deployment failures.
- **Never push directly to main without GitHub Actions secrets set** — the deploy workflow will fail on "Restore required secrets" step if `TDO_API_KEYS`, `EMBEDDER_ENDPOINT`, `EMBEDDER_KEY` are not set in the GitHub "dev" environment.
- **Never run multiple harvest jobs simultaneously** — they share the DB and will contend on upserts; StatFin's rate limit of 0.5 rps also makes parallel jobs fail with 429s.
- **Never deploy using `az containerapp update --image` without also setting all required env vars** — `--set-env-vars` replaces the entire env var set. Always include the three secret refs in the same command.
- **Never try to access Key Vault or PostgreSQL from your local machine** — both are private-endpoint only. Use the API endpoints or run jobs inside the Container Apps environment.
- **Never use `world_bank` or `un_data` as portal_id strings** — the DB stores `worldbank` and `undata`. Adapters and harvest job accept the old aliases but search queries must use the short names.
- **Never use `tdo-job-embed-dev` or `tdo-job-harmonise-dev` as-is** — both still have the placeholder `helloworld` image and do nothing. Use `tdo-job-harvest-dev` with `--env-vars "PORTAL_ID=..."` for now, or call `/v1/admin/backfill-embeddings` for embedding-only runs.

---

## Keeping This File Updated

When you discover a new Azure CLI quirk, fix a recurring bug, or find a gotcha not listed here — update the relevant section of this file in the same commit as the fix. This file is the institutional memory of the project.
