# TDO Platform — Build Tasks

Work through these tasks in order. Do not skip ahead.
After each task: run the test command, fix failures, then mark [x] and commit.

---

## PHASE 1 — Project structure and data models

- [x] **Task 1: Create project file structure**

  Create the following empty directory structure and placeholder __init__.py files:
  ```
  src/
    adapters/
    pipeline/
    api/
    orchestrator/
    models/
  infra/
    modules/
    parameters/
  tests/
    unit/
    integration/
  .github/
    workflows/
  ```
  Also create: `Makefile`, `requirements.txt`, `pyproject.toml`, `.gitignore`

  requirements.txt must include:
  ```
  pydantic>=2.0
  fastapi>=0.110
  uvicorn
  httpx
  asyncpg
  structlog
  pytest
  pytest-asyncio
  hypothesis
  coverage
  python-dotenv
  pgvector
  sqlalchemy[asyncio]
  alembic
  ```

  Test command: `ls src/adapters src/pipeline src/api src/models infra/modules tests/unit`
  Success: all directories exist

---

- [x] **Task 2: Write Pydantic data models**

  Create `src/models/mvm.py` with:
  - `MVMRecord` — the full public MVM schema from tdo_build_prompt_v2.md
  - `InternalProcessingRecord` — the internal audit schema
  - `SearchFilters` — query filter parameters
  - `SearchResult` — single search result with similarity score
  - `PortalHealth` — portal status model

  Use Pydantic v2 throughout. All fields typed. Enums for resource_type,
  access_type, update_frequency, metadata_standard, publisher_type.

  Test command: `python -m pytest tests/unit/test_models.py -v`

  Write the test file `tests/unit/test_models.py` that verifies:
  - MVMRecord rejects records missing required fields
  - MVMRecord accepts valid minimal record
  - All enum fields reject invalid values
  - confidence_score rejects values outside 0.0-1.0

---

- [x] **Task 3: Write database models**

  Create `src/models/db.py` with SQLAlchemy async models matching
  the PostgreSQL schema in tdo_build_prompt_v2.md:
  - `Dataset` table
  - `DatasetVersion` table
  - `DatasetAlias` table
  - `MetadataReviewQueue` table
  - `ProcessingRecord` table
  - `PipelineRun` table

  Create `alembic.ini` and initial migration in `alembic/versions/`.

  Test command: `python -m pytest tests/unit/test_db_models.py -v`

  Write test that verifies all models can be imported and have correct columns.

---

## PHASE 2 — Schema mapping and harmonisation

- [x] **Task 4: Integrate mapping tables**

  Copy `mapping_tables.py` into `src/pipeline/mapping_tables.py`.
  Write `src/pipeline/schema_detector.py` that:
  - Takes a raw dict payload
  - Scans for SCHEMA_DETECTION_SIGNALS
  - Returns the detected schema name
  - Returns "unknown" if no signals match

  Test command: `python -m pytest tests/unit/test_mapping.py -v`

  Write `tests/unit/test_mapping.py` that verifies:
  - SDMX payloads detected as "SDMX"
  - DCAT payloads detected as "DCAT"
  - Dublin Core payloads detected as "DublinCore"
  - DDI payloads detected as "DDI"
  - World Bank payloads detected as "WorldBank"
  - Unknown payloads return "unknown"
  - All frequency codes map to valid values (use hypothesis)
  - _frequency_map never raises on any string input (use hypothesis)
  - _iso_date returns string or None, never raises (use hypothesis)

---

- [x] **Task 5: Write the harmoniser**

  Create `src/pipeline/harmoniser.py` with:
  - `HarmoniserConfig` — settings (LLM endpoints, confidence thresholds)
  - `Harmoniser` class with `async def process(raw, portal_id) -> MVMRecord`
  - Deterministic mapping path (uses mapping_tables.py)
  - Phi-4 LLM path for unmapped fields (Azure AI Foundry serverless)
  - Azure OpenAI fallback path (confidence < 0.3)
  - Field evidence tracking
  - Per-field confidence scoring
  - Overall confidence score calculation
  - completeness_score calculation
  - freshness_score calculation
  - Pydantic validation of output
  - Review queue flagging (confidence < 0.6)

  LLM calls must use the exact system prompt from tdo_build_prompt_v2.md.
  LLM must never populate: dataset_url, publisher, license, temporal fields
  unless they are explicitly present in the raw payload.

  Test command: `python -m pytest tests/unit/test_harmoniser.py -v`

  Write `tests/unit/test_harmoniser.py` that verifies:
  - Harmoniser never invents URLs (pass payload with no URL, assert dataset_url is None)
  - Harmoniser never invents licenses (pass payload with no license, assert license is None)
  - Harmoniser never invents publisher names (pass payload with no publisher)
  - confidence_score is always between 0.0 and 1.0
  - completeness_score is always between 0.0 and 1.0
  - Records with confidence < 0.6 are flagged for review
  - Pydantic validation errors are caught and logged, not raised

---

## PHASE 3 — Portal adapters

- [x] **Task 6: Write the base portal adapter**

  Create `src/adapters/base.py` with:
  - `RawRecord` dataclass (source_id, portal_id, raw_payload, raw_payload_hash,
    adapter_type, fetched_at)
  - `AdapterHealth` dataclass
  - `BasePortalAdapter` abstract class with all methods from tdo_build_prompt_v2.md
  - Rate limiting (asyncio-based, configurable per portal)
  - Retry logic (exponential backoff, max 3 retries, 30s timeout)
  - robots.txt checking for HTML adapters
  - Raw payload hashing (SHA-256)

  Test command: `python -m pytest tests/unit/test_base_adapter.py -v`

  Write test verifying rate limiter enforces delays between calls.

---

- [x] **Task 7: Write Statistics Finland adapter**

  Create `src/adapters/statistics_finland.py`
  Portal: PxWeb REST JSON API
  Base URL: https://pxdata.stat.fi:443/PxWeb/api/v1/en
  
  Implement:
  - Recursive catalogue traversal (folder tree → leaf datasets)
  - fetch_catalogue() yields RawRecord for each dataset
  - fetch_record(source_id) fetches single dataset metadata
  - get_portal_defaults() returns PORTAL_DEFAULTS["statistics_finland"]
  - Incremental harvesting using last-modified timestamps
  - Rate limit: 1 req/sec

  Test command: `python -m pytest tests/unit/test_statfin_adapter.py -v`

  Write unit test using recorded API response (use pytest-recording/VCR).
  Record a real response from the API on first run.
  Test verifies: RawRecord has non-null payload, hash is SHA-256, source_id is set.

---

- [x] **Task 8: Write World Bank adapter**

  Create `src/adapters/world_bank.py`
  Portal: World Bank REST JSON
  Base URL: https://api.worldbank.org/v2
  Catalogue: /sources?format=json&per_page=100
  Topics: /topics?format=json

  Implement pagination, topic enrichment, portal defaults injection.
  Rate limit: 1 req/sec

  Test command: `python -m pytest tests/unit/test_worldbank_adapter.py -v`
  Use VCR cassette for recorded response.

---

- [x] **Task 9: Write Eurostat adapter**

  Create `src/adapters/eurostat.py`
  Portal: SDMX REST 2.1
  Base URL: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1
  Catalogue: /dataflow/ESTAT?detail=allstubs

  Implement incremental delta using updatedAfter parameter.
  Handle large catalogue (~8000 dataflows) with pagination.
  Rate limit: 2 req/sec

  Test command: `python -m pytest tests/unit/test_eurostat_adapter.py -v`
  Use VCR cassette.

---

- [x] **Task 10: Write OECD adapter**

  Create `src/adapters/oecd.py`
  Portal: SDMX REST 2.1
  Base URL: https://sdmx.oecd.org/public/rest
  Catalogue: /dataflow/OECD?detail=allstubs

  Flag sub-national or experimental dataflows as resource_type="table".
  Rate limit: 1 req/sec

  Test command: `python -m pytest tests/unit/test_oecd_adapter.py -v`
  Use VCR cassette.

---

- [ ] **Task 11: Write UN Data adapter**

  Create `src/adapters/un_data.py`
  Portal: SDMX (partial compliance)
  Base URL: http://data.un.org/ws/rest

  Implement aggressive error handling — any parse failure routes to
  schema="unknown" for LLM harmonisation.
  Log all parse failures with full payload for debugging.
  Rate limit: 1 req/sec

  Test command: `python -m pytest tests/unit/test_undata_adapter.py -v`
  Use VCR cassette. Include a test for malformed response handling.

---

## PHASE 4 — Embedding and indexing

- [ ] **Task 12: Write the embedder**

  Create `src/pipeline/embedder.py` with:
  - `EmbedderConfig` — endpoint URL, model ID, expected dimensions
  - `Embedder` class
  - `async def validate_config()` — calls endpoint with test string,
    asserts returned dimension matches config, raises ConfigurationError if not
  - `async def embed(record: MVMRecord) -> list[float]`
  - Embedding input construction:
    "{title} {description} {keywords} {themes} {geographic_coverage} {publisher}"
  - Retry logic (3 retries, exponential backoff)
  - Calls Azure AI Foundry serverless multilingual-e5-large endpoint

  Test command: `python -m pytest tests/unit/test_embedder.py -v`

  Write test that:
  - Mocks the endpoint (use respx)
  - Verifies validate_config raises on dimension mismatch
  - Verifies embed returns list of floats
  - Verifies embedding input string is constructed correctly

---

- [ ] **Task 13: Write the indexer**

  Create `src/pipeline/indexer.py` with:
  - `Indexer` class
  - `async def upsert(record: MVMRecord, embedding: list[float])`
  - Handles insert and update (on conflict update)
  - Writes to dataset_versions table on every upsert
  - Resolves aliases if source_id has changed
  - Updates pipeline_runs table on completion

  Test command: `python -m pytest tests/unit/test_indexer.py -v`
  Use testcontainers PostgreSQL with pgvector for the test.

---

## PHASE 5 — Search API

- [ ] **Task 14: Write hybrid search**

  Create `src/api/search.py` with:
  - `hybrid_search(query, filters, limit, semantic_weight, keyword_weight)`
  - Embed query using multilingual-e5-large
  - Run pgvector cosine similarity search
  - Run PostgreSQL tsvector full-text search ('simple' config)
  - RRF (Reciprocal Rank Fusion) combining both channels
  - Handle edge case: only one channel returns results
  - Apply filters as WHERE clauses before search
  - Return ranked list of SearchResult

  Test command: `python -m pytest tests/unit/test_search.py -v`

  Write tests verifying:
  - RRF scoring formula is correct
  - Filter-only queries work without embedding
  - Single channel fallback works correctly
  - min_confidence filter is applied

---

- [ ] **Task 15: Write FastAPI application**

  Create `src/api/main.py` with all endpoints from tdo_build_prompt_v2.md:
  - GET /v1/datasets
  - GET /v1/datasets/{id}
  - GET /v1/datasets/{id}/similar
  - GET /v1/datasets/{id}/provenance
  - POST /v1/query
  - GET /v1/portals
  - GET /v1/health
  - GET /v1/stats

  Include:
  - API key authentication middleware
  - Structured logging with request IDs
  - CORS middleware
  - OpenAPI docs auto-generated

  Test command: `python -m pytest tests/unit/test_api.py -v`

  Write tests using FastAPI TestClient verifying:
  - All endpoints return correct status codes
  - /v1/health returns 200
  - /v1/datasets validates query parameters
  - Authentication rejects missing API key

---

## PHASE 6 — Orchestration

- [ ] **Task 16: Write Durable Functions orchestrator**

  Create `src/orchestrator/functions.py` with:
  - `harvest_portal` activity function (calls portal adapter)
  - `harmonise_record` activity function (calls harmoniser)
  - `embed_record` activity function (calls embedder)
  - `index_record` activity function (calls indexer)
  - `tdo_pipeline_orchestrator` orchestrator function (fan-out/fan-in)
  - `tdo_scheduler` timer trigger (per-portal schedules)
  - Checkpoint resume logic using pipeline_runs table

  Test command: `python -m pytest tests/unit/test_orchestrator.py -v`

---

## PHASE 7 — Infrastructure

- [ ] **Task 17: Write Bicep infrastructure templates**

  Create all Bicep files from tdo_build_prompt_v2.md:
  - infra/main.bicep
  - infra/parameters/dev.bicepparam
  - infra/modules/network.bicep (VNet, subnets, private DNS, NAT gateway)
  - infra/modules/storage.bicep
  - infra/modules/database.bicep (PostgreSQL + pgvector)
  - infra/modules/containerApps.bicep
  - infra/modules/functions.bicep
  - infra/modules/keyvault.bicep
  - infra/modules/monitoring.bicep (with all alert rules)
  - infra/modules/acr.bicep

  Use parameters for environment, location, tenantId, administratorObjectId.
  All resources use Managed Identities. No secrets in Bicep.

  Test command: `az bicep lint infra/main.bicep`
  Success: no errors

---

- [ ] **Task 18: Write GitHub Actions workflows**

  Create:
  - `.github/workflows/deploy-infra.yml`
    Triggers: push to main, manual dispatch
    Steps: bicep lint → az deployment what-if → az deployment create
    Uses OIDC (no stored credentials)
    Environment: dev (auto), prod (manual approval)

  - `.github/workflows/deploy-app.yml`
    Triggers: after deploy-infra passes
    Steps: docker build → push to ACR → update Container App revisions

  - `.github/workflows/run-integration.yml`
    Triggers: nightly 2am, PR
    Steps: start docker-compose → run pytest tests/integration → stop

  All workflows use:
    permissions:
      id-token: write
      contents: read

  Test command: verify YAML is valid with `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-infra.yml'))"`

---

- [ ] **Task 19: Write docker-compose for local development**

  Create `docker-compose.yml` with services:
  - postgres (pgvector/pgvector:pg16)
  - ollama (for local Phi-4)
  - embeddings (text-embeddings-inference for e5-large)
  - minio (blob storage mock)
  - api (the FastAPI app)

  Create `docker-compose.test.yml` for integration tests.

  Create `.env.example` with all required environment variables documented.

  Test command: `docker-compose config`
  Success: no errors

---

## PHASE 8 — Integration test and frontend

- [ ] **Task 20: Write integration test**

  Create `tests/integration/test_full_pipeline.py` with the integration
  test from tdo_build_prompt_v2.md:

  ```
  test_full_pipeline_statistics_finland:
    1. Harvest one StatFin dataset
    2. Harmonise it
    3. Embed it
    4. Index it
    5. Query for it
    Assert each step passes
  ```

  This test requires docker-compose to be running.

  Test command: `docker-compose -f docker-compose.test.yml up -d; python -m pytest tests/integration/test_full_pipeline.py -v; docker-compose -f docker-compose.test.yml down`

---

- [ ] **Task 21: Wire frontend to real API**

  Update `tdo-demo.jsx`:
  - Replace all mock data with real API calls to the FastAPI backend
  - Search tab calls GET /v1/datasets?q={query}
  - Dashboard tab calls GET /v1/portals and GET /v1/stats
  - Provenance modal calls GET /v1/datasets/{id}/provenance
  - AI summary calls POST /v1/query
  - Add loading states and error handling
  - Add environment variable for API base URL (VITE_API_URL)

  Create `frontend/` directory with:
  - package.json (React + Vite)
  - vite.config.js
  - src/App.jsx (the updated tdo-demo.jsx)

  Test command: `cd frontend; npm install; npm run build`
  Success: build completes without errors

---

## PHASE 9 — Final checks

- [ ] **Task 22: Run full test suite and coverage report**

  ```
  python -m pytest tests/unit -v --tb=short
  python -m pytest tests/unit --cov=src --cov-report=term-missing --cov-fail-under=80
  ```

  Fix any failures. Coverage must be ≥ 80% on src/ before proceeding.

---

- [ ] **Task 23: Write README.md**

  Create `README.md` with:
  - Project overview (what TDO is, what this platform does)
  - Architecture diagram in Mermaid showing the full pipeline
  - Prerequisites
  - Local development setup (docker-compose)
  - Azure deployment instructions
  - How to add a new portal (step by step)
  - API reference summary with example curl commands
  - Troubleshooting section

---

- [ ] **Task 24: Final commit and push**

  ```
  git add .
  git commit -m "TDO Platform — complete Phase 1 build"
  git push origin main
  ```

  Verify GitHub Actions starts running in the Actions tab.
  The deploy-infra workflow will begin deploying to Azure automatically.

---

## BUILD COMPLETE

When all tasks are marked [x] and GitHub Actions deploy-infra has succeeded:

1. Note the API URL from the Azure Container Apps output
2. Update VITE_API_URL in the frontend with the real URL
3. Run: `cd frontend; npm run build`
4. The system is live

Total datasets expected after first full harvest:
- Statistics Finland: ~1,800
- World Bank: ~12,400
- Eurostat: ~8,200
- OECD: ~2,900
- UN Data: ~500
- **Total: ~25,800 datasets indexed**
