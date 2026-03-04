# TDO Build Prompt v2
# Trusted Data Observatory — Azure Implementation
# Revised based on architectural review

---

You are a senior Azure cloud architect and Python engineer. Your task is to
design and implement a full end-to-end automated metadata pipeline for a
Trusted Data Observatory (TDO) — a system that harvests official statistical
portal metadata via APIs, harmonises it, indexes it for semantic search, and
exposes it via a query API.

---

## CORE PRINCIPLES (non-negotiable)

1. **Metadata only.** The TDO describes datasets. It never fetches, stores,
   or proxies actual data. Data ownership and QA remain with the producer.

2. **Trust is explicit and measurable.** Every record carries provenance,
   quality scores, and evidence pointers. The system can always answer:
   "where did this field value come from, and how confident are we?"

3. **LLMs assist; they do not invent.** An LLM may only populate a field if
   it can cite the raw source path it drew from. It must never fabricate:
   - URLs
   - Publisher names (unless present verbatim in the raw payload)
   - License identifiers (unless present verbatim)
   - Temporal coverage dates (unless explicitly stated)

4. **API-first harvesting.** HTML crawling is the exception. Every portal
   has an official API; use it. If robots.txt forbids HTML crawling, do not
   crawl HTML under any circumstances.

5. **Resumable by design.** Every pipeline stage writes its state to
   PostgreSQL before proceeding. A restart from any failure point must
   cost at most one re-run of the failed record, not a full re-crawl.

---

## MVM SCHEMA (public-facing)

```python
class MVMRecord(BaseModel):
    # Identity
    id: str                          # stable internal UUID (not source ID)
    source_id: str                   # ID as given by source portal
    source_id_aliases: list[str]     # previous IDs from same source (for lineage)
    resource_type: Literal[
        "dataset", "table", "indicator", "collection", "unknown"
    ] = "dataset"

    # Descriptive
    title: str
    description: str | None
    publisher: str
    publisher_type: Literal["NSO", "IO", "NGO", "other"]
    source_portal: str               # URL of originating portal
    dataset_url: str | None          # direct URL to dataset landing page
    keywords: list[str] = []
    themes: list[str] = []           # COFOG / SDMX theme codes where available

    # Coverage
    geographic_coverage: list[str] = []   # ISO 3166 codes
    temporal_coverage_start: str | None   # YYYY or YYYY-MM-DD
    temporal_coverage_end: str | None     # YYYY, YYYY-MM-DD, or "ongoing"
    languages: list[str] = []             # ISO 639-1 codes

    # Access
    update_frequency: Literal[
        "daily", "weekly", "monthly", "annual", "irregular"
    ] | None
    last_updated: str | None         # ISO 8601
    access_type: Literal["open", "restricted", "embargoed"]
    access_conditions: str | None
    license: str | None              # SPDX ID or URL
    formats: list[str] = []
    contact_point: str | None

    # Provenance
    provenance: str | None
    metadata_standard: Literal[
        "SDMX", "DCAT", "DublinCore", "DDI", "other", "unknown"
    ]

    # Trust & quality signals (public)
    confidence_score: float          # 0.0–1.0, overall
    completeness_score: float        # fraction of non-null recommended fields
    freshness_score: float           # 1.0 = updated within expected frequency
    link_healthy: bool | None        # dataset_url responded at harvest time

    # System
    ingestion_timestamp: datetime
```

## INTERNAL PROCESSING RECORD (not exposed via API)

```python
class InternalProcessingRecord(BaseModel):
    mvm_id: str                      # FK to MVMRecord.id

    # Auditability
    raw_blob_path: str               # Azure Blob path to raw API response
    raw_payload_hash: str            # SHA-256 of raw response bytes
    parser_version: str              # semver of crawler/adapter
    harmoniser_version: str          # semver of harmoniser
    embedding_model_version: str     # model ID + version string
    pipeline_run_id: str             # Durable Functions instance ID

    # LLM evidence
    field_confidence: dict[str, float]   # per-field confidence
    field_evidence: dict[str, str]       # field → raw_path it was drawn from
    llm_model_used: str | None           # null if deterministic only
    llm_fallback_triggered: bool

    # Review
    flagged_for_review: bool
    review_reason: str | None
```

---

## TARGET PORTALS — IMPLEMENTATION ORDER

Implement in this exact order. Phase 1 is complete only when all five pass
the integration test suite.

### Priority 1 — Statistics Finland (PxWeb API)
- Base: `https://pxdata.stat.fi:443/PxWeb/api/v1/en`
- Protocol: PxWeb REST JSON
- Catalogue endpoint: `/api/v1/en` (returns recursive table/folder tree)
- Notes: folder-first hierarchy; recurse to leaf nodes for actual datasets.
  Smallest portal — use as the integration test baseline.

### Priority 2 — World Bank Open Data
- Base: `https://api.worldbank.org/v2`
- Protocol: World Bank REST JSON
- Catalogue: `/sources?format=json&per_page=100` (paginated)
- Topics: `/topics?format=json` (for keyword enrichment)
- Notes: clean API, permissive CORS, CC-BY 4.0. Good for rapid validation.

### Priority 3 — Eurostat
- Base: `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1`
- Protocol: SDMX REST 2.1
- Catalogue: `/dataflow/ESTAT?detail=allstubs` (returns all dataflow stubs)
- Notes: large catalogue (~8,000 dataflows). Implement incremental delta
  using `updatedAfter` query parameter.

### Priority 4 — OECD
- Base: `https://sdmx.oecd.org/public/rest`
- Protocol: SDMX REST 2.1
- Catalogue: `/dataflow/OECD?detail=allstubs`
- Notes: some dataflows are sub-national or experimental; flag these with
  resource_type="table" unless confirmed as full datasets.

### Priority 5 — UN Data
- Base: `http://data.un.org/ws/rest`
- Protocol: SDMX (partial compliance)
- Notes: API has inconsistent SDMX compliance. Implement with aggressive
  error handling; treat any parse failure as "unknown" schema and route to
  LLM harmonisation. Leave until last — highest effort, lowest API quality.

---

## PORTAL ADAPTER ARCHITECTURE

Define three adapter types. Every portal must use the most preferred
applicable type. HTML adapters require explicit architectural approval.

```
Level 1 — API Adapter (preferred)
  Speaks directly to official REST / SDMX / PxWeb API
  Returns structured JSON or XML
  Examples: all five Phase 1 portals

Level 2 — HTML Adapter (exception only)
  Used only when no catalogue endpoint exists
  Must respect robots.txt — abort if disallowed
  Must implement rate limiting: 1 req/sec default, configurable per portal

Level 3 — Document Adapter (rare)
  For portals that publish catalogue as PDF or spreadsheet
  Routes immediately to LLM extraction; no deterministic mapping
```

```python
class BasePortalAdapter(ABC):
    portal_id: str
    base_url: str
    rate_limit_rps: float = 1.0
    adapter_type: Literal["api", "html", "document"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]
    async def fetch_record(self, source_id: str) -> RawRecord
    async def check_robots(self) -> bool        # Level 2 only
    async def health_check(self) -> AdapterHealth
    def get_portal_defaults(self) -> dict       # injects known publisher, licence etc.
```

---

## PIPELINE STAGES

Orchestrated by **Azure Durable Functions** (fan-out/fan-in pattern).
Compute executed in **Azure Container Apps Jobs** (invoked by orchestrator).
Do not mix these; Durable Functions orchestrates, Container Apps Jobs execute.

```
[Scheduler]
    │
    ▼
[Orchestrator — Durable Function]
    │
    ├──► Stage 1: HARVEST    (Container Apps Job per portal, parallelised)
    │        Raw response → Blob Storage (cold, audit)
    │        State written to pipeline_runs table on completion
    │
    ├──► Stage 2: DETECT     (inline, fast)
    │        Detect schema type from raw payload signals
    │        Select mapping table
    │
    ├──► Stage 3: HARMONISE  (Container Apps Job)
    │        Apply deterministic field mapping tables first
    │        For unmapped/ambiguous fields: call Phi-4 with evidence rule
    │        If confidence < 0.6: flag for human review queue
    │        If confidence < 0.3: escalate to Azure OpenAI gpt-4o (fallback)
    │        Validate with Pydantic; reject invalid records
    │        Compute completeness_score, freshness_score
    │
    ├──► Stage 4: LINK CHECK (async, non-blocking)
    │        HEAD request to dataset_url
    │        Write link_healthy to record; do not block indexing
    │
    ├──► Stage 5: EMBED      (Container Apps Job)
    │        Build embedding string from title + description + keywords
    │         + themes + geographic_coverage + publisher
    │        Call multilingual-e5-large endpoint
    │        Validate embedding_dim at runtime against config value
    │        Fail fast (do not store) if dim mismatch
    │
    └──► Stage 6: INDEX      (inline)
             Upsert to PostgreSQL datasets table
             Update dataset_versions table
             Resolve aliases if source_id changed
```

### Pipeline state table (PostgreSQL)

```sql
CREATE TABLE pipeline_runs (
    run_id          UUID PRIMARY KEY,
    portal_id       TEXT NOT NULL,
    stage           TEXT NOT NULL,    -- harvest|detect|harmonise|embed|index
    status          TEXT NOT NULL,    -- pending|running|complete|failed
    source_id       TEXT,             -- null at harvest level, populated per-record
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    retry_count     INT DEFAULT 0
);
-- Compound index for checkpoint resume
CREATE INDEX idx_pipeline_resume ON pipeline_runs(portal_id, stage, status);
```

---

## DATA MODEL (PostgreSQL)

```sql
-- Core record (current version materialised)
CREATE TABLE datasets (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               TEXT NOT NULL,
    portal_id               TEXT NOT NULL,
    current_version_id      UUID REFERENCES dataset_versions(id),
    resource_type           TEXT NOT NULL DEFAULT 'dataset',
    title                   TEXT NOT NULL,
    description             TEXT,
    publisher               TEXT NOT NULL,
    publisher_type          TEXT NOT NULL,
    source_portal           TEXT,
    dataset_url             TEXT,
    keywords                TEXT[],
    themes                  TEXT[],
    geographic_coverage     TEXT[],
    temporal_coverage_start TEXT,
    temporal_coverage_end   TEXT,
    languages               TEXT[],
    update_frequency        TEXT,
    last_updated            TEXT,
    access_type             TEXT NOT NULL,
    access_conditions       TEXT,
    license                 TEXT,
    formats                 TEXT[],
    contact_point           TEXT,
    provenance              TEXT,
    metadata_standard       TEXT,
    confidence_score        FLOAT,
    completeness_score      FLOAT,
    freshness_score         FLOAT,
    link_healthy            BOOLEAN,
    ingestion_timestamp     TIMESTAMPTZ,
    -- Search vectors (updated by trigger)
    fts_en   tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''))
    ) STORED,
    -- Embedding
    embedding               vector(1024),   -- dim validated at runtime
    UNIQUE(source_id, portal_id)
);

-- Version history
CREATE TABLE dataset_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID REFERENCES datasets(id),
    version_number  INT NOT NULL,
    mvm_snapshot    JSONB NOT NULL,         -- full MVM at this version
    pipeline_run_id UUID,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Alias table (handles source ID changes)
CREATE TABLE dataset_aliases (
    alias_source_id TEXT NOT NULL,
    portal_id       TEXT NOT NULL,
    canonical_id    UUID REFERENCES datasets(id),
    first_seen      TIMESTAMPTZ,
    PRIMARY KEY (alias_source_id, portal_id)
);

-- Human review queue
CREATE TABLE metadata_review_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID REFERENCES datasets(id),
    pipeline_run_id UUID,
    confidence_score FLOAT,
    field_confidence JSONB,
    field_evidence   JSONB,
    review_reason   TEXT,
    reviewed        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Internal processing records
CREATE TABLE processing_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mvm_id                  UUID REFERENCES datasets(id),
    raw_blob_path           TEXT,
    raw_payload_hash        TEXT,
    parser_version          TEXT,
    harmoniser_version      TEXT,
    embedding_model_version TEXT,
    pipeline_run_id         UUID,
    field_confidence        JSONB,
    field_evidence          JSONB,
    llm_model_used          TEXT,
    llm_fallback_triggered  BOOLEAN,
    flagged_for_review      BOOLEAN,
    review_reason           TEXT
);

-- Indexes
CREATE INDEX ON datasets USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON datasets USING gin(fts_en);
CREATE INDEX ON datasets (portal_id, last_updated DESC);
CREATE INDEX ON datasets (access_type);
CREATE INDEX ON datasets USING gin(geographic_coverage);
CREATE INDEX ON datasets USING gin(keywords);
```

---

## HARMONISATION RULES

### Deterministic mapping (fast path — no LLM)

Apply field mapping tables from `pipeline/mapping_tables.py`.
Order of precedence:
1. Portal defaults (injected by adapter)
2. Deterministic field map for detected schema
3. Cross-schema fallbacks (e.g. try DCAT path if SDMX path returns null)

### LLM harmonisation (Phi-4 — slow path)

Only called for fields that deterministic mapping could not populate.

**System prompt (exact — do not modify without versioning):**
```
You are a metadata harmonisation specialist for official statistical data.
Your task is to extract specific fields from a raw metadata record and map
them to the provided JSON schema.

Rules you must follow without exception:
1. Only populate a field if you can identify WHERE in the raw payload the
   value comes from. For each field you populate, include the source path
   in field_evidence.
2. Never invent or infer: URLs, publisher names, license identifiers, or
   dates. If not present in the raw payload, return null for that field.
3. Return only valid JSON matching the target schema.
4. Set field_confidence for each field you populate (0.0–1.0).
5. Set overall confidence_score as the mean of field_confidence values,
   weighted by field importance (title=0.2, description=0.15,
   publisher=0.15, geographic_coverage=0.1, temporal=0.1, rest=0.05 each).
```

**User prompt template:**
```
Source schema: {schema_type}
Portal: {portal_id}

Raw metadata payload:
{raw_json}

Fields already populated by deterministic mapping (do not re-populate):
{already_mapped_fields}

Fields requiring extraction:
{unmapped_fields}

Target schema for unmapped fields:
{partial_mvm_schema}

Return JSON only. No preamble.
```

### Quality scores (computed deterministically post-harmonisation)

```python
RECOMMENDED_FIELDS = {
    "title", "description", "publisher", "geographic_coverage",
    "temporal_coverage_start", "update_frequency", "last_updated",
    "access_type", "license", "formats", "keywords"
}

def completeness_score(record: MVMRecord) -> float:
    populated = sum(
        1 for f in RECOMMENDED_FIELDS
        if getattr(record, f, None) not in (None, [], "")
    )
    return populated / len(RECOMMENDED_FIELDS)

def freshness_score(record: MVMRecord) -> float:
    """1.0 = updated within expected frequency window."""
    if not record.last_updated or not record.update_frequency:
        return 0.5   # unknown; neutral
    freq_days = {"daily": 1, "weekly": 7, "monthly": 31,
                 "annual": 366, "irregular": 730}
    expected = freq_days.get(record.update_frequency, 730)
    try:
        last = datetime.fromisoformat(record.last_updated)
        age_days = (datetime.utcnow() - last).days
        return max(0.0, 1.0 - (age_days / (expected * 2)))
    except ValueError:
        return 0.5
```

---

## SEARCH API (FastAPI)

### Endpoints

```
GET  /v1/datasets
     q          — natural language query (triggers hybrid search)
     geo        — ISO 3166 code(s), comma-separated
     theme      — theme code(s)
     publisher  — publisher name (fuzzy match)
     format     — format string
     access     — open | restricted | embargoed
     resource_type — dataset | table | indicator | collection
     updated_after — ISO date
     min_confidence — float (default 0.5)
     limit      — int (default 20, max 100)
     offset     — int

GET  /v1/datasets/{id}
     Full MVM record

GET  /v1/datasets/{id}/similar
     Top-10 semantically similar datasets (cosine, vector only)

GET  /v1/datasets/{id}/provenance
     Returns InternalProcessingRecord for this dataset
     Requires elevated API scope (not public)

POST /v1/query
     Body: { "question": "..." }
     Phi-4 decomposes question → structured /datasets params
     Returns: structured results + natural language summary

GET  /v1/portals
     List all portals, last crawl timestamp, record count, avg quality scores

GET  /v1/health
     Pipeline status per portal, queue depths, model endpoint health

GET  /v1/stats
     Aggregate counts by portal, theme, geo, access_type, resource_type
```

### Hybrid search implementation

```python
async def hybrid_search(
    query: str,
    filters: SearchFilters,
    limit: int = 20,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[SearchResult]:
    """
    RRF (Reciprocal Rank Fusion) over:
      - pgvector cosine similarity (semantic)
      - PostgreSQL tsvector full-text ('simple' config — not 'english',
        to avoid stemming failures on multilingual content)

    Normalisation:
      - Both channels ranked 1..N before fusion
      - RRF score = sum(1 / (k + rank)) where k=60
      - Final score = semantic_weight * rrf_semantic
                    + keyword_weight * rrf_keyword

    Edge cases:
      - If only one channel returns results: use that channel directly,
        log which channel was used in response metadata
      - Filters applied as WHERE clauses before both channels
        (not as post-filter on results)
      - min_confidence filter applied before search
    """
```

---

## AZURE ARCHITECTURE

### Region & networking
- Primary region: **North Europe**
- Failover storage replication: West Europe
- All PaaS services behind Private Endpoints
- Container Apps Environment in VNet-integrated mode
- Outbound egress via NAT Gateway (fixed IP for portal API allowlisting)
- Private DNS zones: one per service (blob, postgres, keyvault, acr,
  aml, apim)
- Model endpoint access: AML managed online endpoints on private VNet;
  Container Apps calls via private DNS

### Services

| Purpose | Service | Notes |
|---|---|---|
| Orchestration | Azure Durable Functions | Fan-out/fan-in per portal |
| Execution units | Azure Container Apps Jobs | Invoked by orchestrator |
| API | Azure Container Apps (always-on) | FastAPI |
| Container registry | Azure Container Registry | Geo-replicated |
| Raw storage | Azure Blob (cold) | Audit archive |
| Processed storage | Azure Blob (hot) | MVM JSON |
| Database | Azure PostgreSQL Flexible Server + pgvector | Primary store |
| Embeddings | AML Managed Online Endpoint — multilingual-e5-large | Apache 2.0 |
| Harmonisation LLM | AML Managed Online Endpoint — Phi-4 | MIT licence |
| LLM fallback | Azure OpenAI — gpt-4o + text-embedding-3-large | Cost-gated |
| Gateway | Azure API Management | Rate limit, auth, versioning |
| Secrets | Azure Key Vault | All credentials |
| Identity | Managed Identity (system-assigned per service) | No secrets in code |
| Monitoring | Azure Monitor + Log Analytics + App Insights | Alerts below |

### Embedding dimension validation (runtime)

```python
# In embedder.py — run at startup before processing any records
async def validate_embedding_config(endpoint: AMLEndpoint) -> int:
    test_embedding = await endpoint.embed(["test"])
    actual_dim = len(test_embedding[0])
    configured_dim = settings.embedding_dim  # from Key Vault / config
    if actual_dim != configured_dim:
        raise ConfigurationError(
            f"Embedding dim mismatch: endpoint returns {actual_dim}, "
            f"config specifies {configured_dim}. "
            f"Update EMBEDDING_DIM in config and run migration if needed."
        )
    return actual_dim
```

### Alert rules

| Alert | Condition | Severity |
|---|---|---|
| Crawl failure | Any portal harvest stage fails 3x | P1 |
| Low confidence | >20% of records in a run have confidence < 0.6 | P2 |
| Pipeline stall | No stage completion for portal in 2x expected duration | P2 |
| Model endpoint unhealthy | Health check fails | P1 |
| Review queue backlog | >500 unreviewed records | P3 |
| Link health degradation | >30% broken URLs for a portal | P3 |
| Embedding dim mismatch | Any occurrence | P1 |

---

## INFRASTRUCTURE AS CODE (Bicep)

Generate complete Bicep templates:

```
infra/
  main.bicep                    — orchestrates all modules
  parameters/
    dev.bicepparam
    staging.bicepparam
    prod.bicepparam
  modules/
    network.bicep               — VNet, subnets, NSGs, NAT gateway,
                                  private DNS zones
    storage.bicep               — Blob (cold + hot), lifecycle policies
    database.bicep              — PostgreSQL Flexible, pgvector,
                                  schemas, indexes, connection pooler
    containerApps.bicep         — Environment (VNet-integrated),
                                  Jobs (harvest, harmonise, embed),
                                  App (api)
    aiml.bicep                  — AML Workspace, compute, online
                                  endpoints (e5-large + Phi-4)
    functions.bicep             — Durable Functions App + storage account
    apim.bicep                  — APIM, products, subscriptions,
                                  rate-limit policy (100 req/min/key)
    keyvault.bicep              — Key Vault, RBAC for all MIs
    monitoring.bicep            — Log Analytics, App Insights, alerts
    acr.bicep                   — Container Registry, geo-replication
```

Parameters for `main.bicep`:
```bicep
param environment string       // dev | staging | prod
param location string = 'northeurope'
param tenantId string
param administratorObjectId string
param embeddingDim int = 1024  // validated at runtime; must match model
```

---

## CI/CD

### GitHub Actions workflows

```
.github/workflows/
  deploy-infra.yml    — bicep lint → what-if → deploy
                        trigger: push to main OR manual dispatch
                        environments: staging (auto), prod (manual approval)

  deploy-app.yml      — docker build → push ACR → update Container App
                        revisions → smoke tests
                        trigger: push to main (after infra passes)

  run-integration.yml — end-to-end: harvest StatFin → harmonise →
                        embed → index → query
                        trigger: nightly + PR
```

### Local development (docker-compose)

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: tdo_dev
    ports: ["5432:5432"]

  ollama:
    image: ollama/ollama
    # Pull Phi-4 on first run: docker exec ollama ollama pull phi4
    ports: ["11434:11434"]

  embeddings:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.5
    command: --model-id intfloat/multilingual-e5-large
    ports: ["8080:80"]

  minio:
    image: minio/minio
    command: server /data
    ports: ["9000:9000", "9001:9001"]

  api:
    build: .
    depends_on: [postgres, ollama, embeddings, minio]
    environment:
      DATABASE_URL: postgresql://postgres@postgres/tdo_dev
      BLOB_ENDPOINT: http://minio:9000
      EMBEDDING_ENDPOINT: http://embeddings:80
      LLM_ENDPOINT: http://ollama:11434
      EMBEDDING_DIM: 1024
    ports: ["8000:8000"]
```

---

## CODE STANDARDS

- Python 3.12, type hints throughout
- Pydantic v2 for all models
- `async` throughout — `httpx.AsyncClient` for HTTP, `asyncpg` for DB
- `structlog` for structured logging with `run_id`, `portal_id`,
  `source_id`, `stage` as bound context on every log line
- All LLM calls: exponential backoff (max 3 retries), 30s timeout,
  circuit breaker after 5 consecutive failures
- `pytest-asyncio` for tests; target 80% coverage on pipeline logic
- All secrets via Managed Identity or Key Vault reference — zero
  plaintext secrets in code, config files, or environment variables

---

## DELIVERABLES (in order)

1. Project file structure (full tree)
2. Bicep templates — `network.bicep` first (everything else depends on it)
3. `models/mvm.py` — Pydantic MVMRecord + InternalProcessingRecord
4. `models/db.py` — SQLAlchemy/asyncpg table definitions matching SQL above
5. `pipeline/mapping_tables.py` — all five schema mapping dicts + helpers
6. `adapters/base.py` — BasePortalAdapter ABC
7. `adapters/statistics_finland.py` — Priority 1 (PxWeb)
8. `adapters/world_bank.py` — Priority 2
9. `adapters/eurostat.py` — Priority 3
10. `adapters/oecd.py` — Priority 4
11. `adapters/un_data.py` — Priority 5 (last, most defensive)
12. `pipeline/schema_detector.py`
13. `pipeline/harmoniser.py` — deterministic + Phi-4 + gpt-4o fallback
14. `pipeline/quality_scorer.py` — completeness + freshness + link check
15. `pipeline/embedder.py` — with dim validation at startup
16. `orchestrator/functions.py` — Durable Functions fan-out/fan-in
17. `api/main.py` — FastAPI with all endpoints
18. `api/search.py` — hybrid search (RRF) implementation
19. GitHub Actions workflows (3 files)
20. `docker-compose.yml`
21. `README.md` — setup, architecture diagram (Mermaid), adding-new-portals guide

---

## INTEGRATION TEST SPEC

The following must pass before Phase 1 is considered complete:

```python
async def test_full_pipeline_statistics_finland():
    """
    End-to-end: harvest one StatFin dataset → harmonise → embed → index → query
    """
    # 1. Harvest
    adapter = StatisticsFinalandAdapter()
    record = await adapter.fetch_record("StatFin/tym/tyonv/")
    assert record.raw_payload is not None
    assert record.raw_payload_hash is not None

    # 2. Harmonise
    mvm = await harmoniser.process(record)
    assert mvm.title is not None
    assert mvm.publisher == "Statistics Finland"
    assert mvm.confidence_score >= 0.6
    assert mvm.completeness_score >= 0.5
    # LLM must not have invented these
    assert mvm.dataset_url is None or mvm.dataset_url.startswith("https://")

    # 3. Embed
    result = await embedder.embed(mvm)
    assert len(result.embedding) == settings.embedding_dim

    # 4. Index
    await indexer.upsert(mvm, result)
    fetched = await db.get_dataset(mvm.id)
    assert fetched is not None

    # 5. Query
    results = await search.hybrid_search("Finnish labour market statistics")
    assert any(r.id == mvm.id for r in results)
```
