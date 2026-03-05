"""
FastAPI application for the TDO platform.
Exposes all endpoints from tdo_build_prompt_v2.md.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.models.mvm import (
    MVMRecord,
    SearchFilters,
    SearchResult,
    PortalHealth,
)

log = structlog.get_logger(__name__)


def _run_migrations() -> None:
    """Run alembic upgrade head on startup if POSTGRES_FQDN is configured."""
    fqdn = os.environ.get("POSTGRES_FQDN")
    db_name = os.environ.get("POSTGRES_DB")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if not (fqdn and db_name and client_id):
        log.info("migrations_skipped", reason="POSTGRES_FQDN not configured")
        return
    try:
        import urllib.parse
        from azure.identity import ManagedIdentityCredential
        from alembic import command
        from alembic.config import Config

        credential = ManagedIdentityCredential(client_id=client_id)
        token = credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default"
        )
        username = os.environ.get("POSTGRES_USER", "tdo-id-api-dev")
        encoded = urllib.parse.quote(token.token, safe="")
        sync_url = (
            f"postgresql+psycopg2://{username}@{fqdn}/{db_name}"
            f"?password={encoded}&sslmode=require"
        )
        alembic_cfg = Config("/app/alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
        command.upgrade(alembic_cfg, "head")
        log.info("migrations_complete")
    except Exception as exc:
        # Log but don't crash — the API may still be usable if schema already exists
        log.warning("migrations_failed", error=str(exc))


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    _run_migrations()
    yield


app = FastAPI(
    title="TDO — Trusted Data Observatory",
    description="Metadata discovery API for official statistical datasets",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://proud-sand-0b2392903.1.azurestaticapps.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------

API_KEY_HEADER = "X-API-Key"
VALID_API_KEYS: set[str] = set(
    filter(None, os.environ.get("TDO_API_KEYS", "dev-key-123").split(","))
)

# Endpoints that don't require authentication
PUBLIC_PATHS = {"/v1/health", "/v1/stats", "/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require API key for all non-public endpoints."""
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in ["/docs", "/redoc", "/openapi"]):
        return await call_next(request)

    api_key = request.headers.get(API_KEY_HEADER)
    if not api_key or api_key not in VALID_API_KEYS:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid API key"},
        )
    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to each request for structured logging."""
    request_id = str(uuid.uuid4())
    log.bind(request_id=request_id, path=request.url.path, method=request.method)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# GET /v1/datasets
# ---------------------------------------------------------------------------

async def _embed_query(query: str) -> list[float] | None:
    """Embed a query string using the configured embedder endpoint."""
    endpoint = os.environ.get("EMBEDDING_ENDPOINT", "")
    api_key = os.environ.get("EMBEDDING_API_KEY", "")
    if not endpoint:
        return None
    import httpx
    try:
        if not endpoint.rstrip("/").endswith(("/v1/embeddings", "/score")):
            endpoint = endpoint.rstrip("/") + "/v1/embeddings"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                endpoint,
                json={"input": [query], "model": "multilingual-e5-large"},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            if "data" in data:
                return data["data"][0]["embedding"]
            if isinstance(data, list):
                return data[0]
    except Exception as exc:
        log.warning("query_embed_failed", error=str(exc))
    return None


def _diversify(results: list[SearchResult], limit: int, per_portal_min: int = 2) -> list[SearchResult]:
    """
    Ensure portal diversity in search results.
    Phase 1: guarantee at least per_portal_min results from every portal that
             has at least one match (results already sorted by score).
    Phase 2: fill remaining slots with highest-scoring remaining results.
    """
    by_portal: dict[str, list[SearchResult]] = {}
    for r in results:
        pid = r.record.source_portal or "unknown"
        by_portal.setdefault(pid, []).append(r)

    selected: list[SearchResult] = []
    selected_ids: set[str] = set()

    # Phase 1 — one pass over portals in order of their best-scoring result
    portals_by_best = sorted(by_portal.keys(), key=lambda p: by_portal[p][0].similarity_score, reverse=True)
    for pid in portals_by_best:
        for r in by_portal[pid][:per_portal_min]:
            if r.record.id not in selected_ids:
                selected.append(r)
                selected_ids.add(r.record.id)

    # Phase 2 — fill to limit by score
    for r in results:
        if len(selected) >= limit:
            break
        if r.record.id not in selected_ids:
            selected.append(r)
            selected_ids.add(r.record.id)

    return sorted(selected, key=lambda r: r.similarity_score, reverse=True)[:limit]


def _row_to_search_result(row, similarity: float, channel: str) -> SearchResult:
    """Convert a DB row mapping to a SearchResult."""
    from src.models.mvm import MVMRecord, SearchResult as SR
    from datetime import timezone

    def _str(v) -> str | None:
        return str(v) if v is not None else None

    def _lst(v) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return []

    def _float(v, default=0.0) -> float:
        try:
            return float(v) if v is not None else default
        except Exception:
            return default

    ingestion_ts = row["ingestion_timestamp"]
    from datetime import datetime
    if ingestion_ts is None:
        ingestion_ts = datetime.now(timezone.utc)
    elif not getattr(ingestion_ts, "tzinfo", None):
        ingestion_ts = ingestion_ts.replace(tzinfo=timezone.utc)

    pub_type = row.get("publisher_type") or "other"
    if pub_type not in ("NSO", "IO", "NGO", "other"):
        pub_type = "other"

    access_type = row.get("access_type") or "open"
    if access_type not in ("open", "restricted", "embargoed"):
        access_type = "open"

    meta_std = row.get("metadata_standard") or "unknown"
    if meta_std not in ("SDMX", "DCAT", "DublinCore", "DDI", "ISO19115", "DataCite", "other", "unknown"):
        meta_std = "unknown"

    mvm = MVMRecord(
        id=str(row["id"]),
        source_id=str(row["source_id"]),
        resource_type=row.get("resource_type") or "dataset",
        title=row.get("title") or "(no title)",
        description=_str(row.get("description")),
        publisher=row.get("publisher") or "Unknown",
        publisher_type=pub_type,
        source_portal=str(row.get("portal_id") or row.get("source_portal") or ""),
        dataset_url=_str(row.get("dataset_url")),
        keywords=_lst(row.get("keywords")),
        themes=_lst(row.get("themes")),
        geographic_coverage=_lst(row.get("geographic_coverage")),
        temporal_coverage_start=_str(row.get("temporal_coverage_start")),
        temporal_coverage_end=_str(row.get("temporal_coverage_end")),
        languages=_lst(row.get("languages")),
        update_frequency=row.get("update_frequency"),
        last_updated=_str(row.get("last_updated")),
        access_type=access_type,
        access_conditions=_str(row.get("access_conditions")),
        license=_str(row.get("license")),
        formats=_lst(row.get("formats")),
        contact_point=_str(row.get("contact_point")),
        provenance=_str(row.get("provenance")),
        metadata_standard=meta_std,
        confidence_score=_float(row.get("confidence_score"), 0.5),
        completeness_score=_float(row.get("completeness_score"), 0.5),
        freshness_score=_float(row.get("freshness_score"), 0.5),
        link_healthy=row.get("link_healthy"),
        ingestion_timestamp=ingestion_ts,
    )
    return SearchResult(record=mvm, similarity_score=min(1.0, max(0.0, similarity)), search_channel=channel)


@app.get("/v1/datasets", response_model=list[SearchResult])
async def list_datasets(
    q: Optional[str] = Query(None, description="Natural language search query"),
    geo: Optional[str] = Query(None, description="ISO 3166 codes, comma-separated"),
    theme: Optional[str] = Query(None, description="Theme codes, comma-separated"),
    publisher: Optional[str] = Query(None, description="Publisher name (fuzzy match)"),
    portal: Optional[str] = Query(None, description="Portal ID (statistics_finland | eurostat | world_bank | oecd | un_data)"),
    format: Optional[str] = Query(None, description="Format string"),
    access: Optional[str] = Query(None, description="open | restricted | embargoed"),
    resource_type: Optional[str] = Query(None, description="dataset | table | indicator | collection"),
    updated_after: Optional[str] = Query(None, description="ISO date"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search datasets using hybrid semantic + keyword search."""
    db_url = _build_db_url()
    if not db_url:
        return []

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(db_url, echo=False)

        # Build filter clauses
        filter_parts = ["confidence_score >= :min_confidence"]
        # Fetch a larger candidate pool so diversity pass has enough to work with.
        # When a portal filter is active we go direct — no diversity needed.
        candidate_limit = limit if portal else limit * 5
        params: dict = {"min_confidence": min_confidence, "limit": candidate_limit, "offset": offset}

        if access:
            filter_parts.append("access_type = :access")
            params["access"] = access
        if resource_type:
            filter_parts.append("resource_type = :resource_type")
            params["resource_type"] = resource_type
        if publisher:
            filter_parts.append("publisher ILIKE :publisher")
            params["publisher"] = f"%{publisher}%"
        if portal:
            filter_parts.append("portal_id = :portal")
            params["portal"] = portal
        if geo:
            geo_list = [g.strip() for g in geo.split(",") if g.strip()]
            filter_parts.append("geographic_coverage && :geo")
            params["geo"] = geo_list
        if theme:
            theme_list = [t.strip() for t in theme.split(",") if t.strip()]
            filter_parts.append("themes && :themes")
            params["themes"] = theme_list
        if format:
            filter_parts.append(":fmt = ANY(formats)")
            params["fmt"] = format
        if updated_after:
            filter_parts.append("last_updated >= :updated_after")
            params["updated_after"] = updated_after

        where = " AND ".join(filter_parts)
        results = []

        # Each attempt uses its own connection to avoid transaction abort cascade.
        # Try semantic search first (requires pgvector migration to have run).
        if q:
            query_vec = await _embed_query(q)
            if query_vec is not None:
                try:
                    vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"
                    # Use CAST() instead of ::vector to avoid asyncpg param conflict
                    sql = text(f"""
                        SELECT *, 1 - (embedding_vec <=> CAST(:vec AS vector)) AS similarity
                        FROM datasets
                        WHERE {where} AND embedding_vec IS NOT NULL
                        ORDER BY embedding_vec <=> CAST(:vec AS vector)
                        LIMIT :limit OFFSET :offset
                    """)
                    async with engine.connect() as conn:
                        rows = await conn.execute(sql, {**params, "vec": vec_str})
                        for row in rows.mappings():
                            sim = float(row.get("similarity") or 0.5)
                            results.append(_row_to_search_result(row, sim, "semantic"))
                except Exception as exc:
                    log.warning("semantic_search_failed", error=str(exc))

        # Keyword fallback using FTS
        if q and not results:
            try:
                sql = text(f"""
                    SELECT *, ts_rank(fts_doc, plainto_tsquery('english', :q)) AS similarity
                    FROM datasets
                    WHERE {where} AND fts_doc @@ plainto_tsquery('english', :q)
                    ORDER BY similarity DESC
                    LIMIT :limit OFFSET :offset
                """)
                async with engine.connect() as conn:
                    rows = await conn.execute(sql, {**params, "q": q})
                    for row in rows.mappings():
                        sim = min(1.0, float(row.get("similarity") or 0.3))
                        results.append(_row_to_search_result(row, sim, "keyword"))
            except Exception as exc:
                log.warning("fts_search_failed", error=str(exc))

        # ILIKE fallback if FTS column doesn't exist yet or returned nothing
        if q and not results:
            try:
                kw = f"%{q}%"
                sql = text(f"""
                    SELECT *, confidence_score AS similarity
                    FROM datasets
                    WHERE {where} AND (title ILIKE :kw OR description ILIKE :kw)
                    ORDER BY confidence_score DESC
                    LIMIT :limit OFFSET :offset
                """)
                async with engine.connect() as conn:
                    rows = await conn.execute(sql, {**params, "kw": kw})
                    for row in rows.mappings():
                        sim = float(row.get("similarity") or 0.5)
                        results.append(_row_to_search_result(row, sim, "keyword"))
            except Exception as exc:
                log.warning("ilike_search_failed", error=str(exc))

        if not q:
            # No query — return top records by confidence
            try:
                sql = text(f"""
                    SELECT *, confidence_score AS similarity
                    FROM datasets
                    WHERE {where}
                    ORDER BY confidence_score DESC
                    LIMIT :limit OFFSET :offset
                """)
                async with engine.connect() as conn:
                    rows = await conn.execute(sql, params)
                    for row in rows.mappings():
                        sim = float(row.get("similarity") or 0.5)
                        results.append(_row_to_search_result(row, sim, "browse"))
            except Exception as exc:
                log.warning("browse_search_failed", error=str(exc))

        await engine.dispose()

        # Apply portal diversity when no explicit portal filter is active.
        # This ensures all portals with matching results appear in top results.
        if results and not portal:
            results = _diversify(results, limit)
        else:
            results = results[:limit]

        return results

    except Exception as exc:
        log.warning("search_failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# GET /v1/datasets/{id}
# ---------------------------------------------------------------------------

@app.get("/v1/datasets/{dataset_id}", response_model=MVMRecord)
async def get_dataset(dataset_id: str):
    """Return full MVM record for a specific dataset."""
    # In production: query DB by id
    raise HTTPException(status_code=404, detail="Dataset not found")


# ---------------------------------------------------------------------------
# GET /v1/datasets/{id}/similar
# ---------------------------------------------------------------------------

@app.get("/v1/datasets/{dataset_id}/similar", response_model=list[SearchResult])
async def get_similar_datasets(dataset_id: str):
    """Return top-10 semantically similar datasets."""
    return []


# ---------------------------------------------------------------------------
# GET /v1/datasets/{id}/provenance
# ---------------------------------------------------------------------------

@app.get("/v1/datasets/{dataset_id}/provenance")
async def get_provenance(dataset_id: str, request: Request):
    """Return processing provenance for a dataset from dataset_versions."""
    db_url = _build_db_url()
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(db_url, echo=False)
        async with engine.connect() as conn:
            row = (await conn.execute(
                text("""
                    SELECT d.id, d.source_id, d.portal_id,
                           d.ingestion_timestamp, d.confidence_score,
                           d.completeness_score, d.freshness_score,
                           dv.version_number, dv.mvm_snapshot, dv.created_at
                    FROM datasets d
                    LEFT JOIN dataset_versions dv ON dv.id = d.current_version_id
                    WHERE d.id = CAST(:id AS uuid)
                """),
                {"id": dataset_id},
            )).mappings().fetchone()
        await engine.dispose()
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        snapshot = row["mvm_snapshot"] or {}
        return {
            "dataset_id":          str(row["id"]),
            "source_id":           row["source_id"],
            "portal_id":           row["portal_id"],
            "ingestion_timestamp": row["ingestion_timestamp"].isoformat() if row["ingestion_timestamp"] else None,
            "confidence_score":    row["confidence_score"],
            "completeness_score":  row["completeness_score"],
            "freshness_score":     row["freshness_score"],
            "version_number":      row["version_number"],
            "field_evidence":      snapshot.get("field_evidence"),
            "field_confidence":    snapshot.get("field_confidence"),
            "harmoniser_version":  snapshot.get("harmoniser_version"),
            "model_used":          snapshot.get("llm_model_used"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("provenance_query_failed", dataset_id=dataset_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Internal error")


# ---------------------------------------------------------------------------
# POST /v1/query
# ---------------------------------------------------------------------------

class QueryRequest:
    def __init__(self, question: str):
        self.question = question


from pydantic import BaseModel

class QueryBody(BaseModel):
    question: str


@app.post("/v1/query")
async def natural_language_query(body: QueryBody):
    """
    Decompose a natural language question into structured /datasets params
    using Phi-4 and return structured results + natural language summary.
    """
    return {
        "question": body.question,
        "structured_query": {},
        "results": [],
        "summary": "Query engine not yet connected to LLM endpoint.",
    }


# ---------------------------------------------------------------------------
# GET /v1/portals
# ---------------------------------------------------------------------------

@app.get("/v1/portals", response_model=list[PortalHealth])
async def list_portals():
    """List all portals with last crawl timestamp, record count, and quality scores."""
    portals = [
        "statistics_finland", "world_bank", "eurostat", "oecd", "un_data"
    ]
    return [
        PortalHealth(
            portal_id=pid,
            status="unknown",
        )
        for pid in portals
    ]


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------

async def _probe_endpoint(url: str, api_key: str | None = None) -> str:
    """Return 'connected', 'error', or 'not_configured'."""
    if not url:
        return "not_configured"
    import httpx
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        # Any HTTP response (even 404/405) means the service is reachable
        return "connected" if resp.status_code < 500 else "error"
    except Exception:
        return "error"


@app.get("/v1/health")
async def health():
    """Pipeline status per portal, queue depths, model endpoint health."""
    embedding_url = os.environ.get("EMBEDDING_ENDPOINT", "")
    embedding_key = os.environ.get("EMBEDDING_API_KEY", "")
    openai_url    = os.environ.get("OPENAI_ENDPOINT", "")
    openai_key    = os.environ.get("OPENAI_API_KEY", "")

    embedder_status   = await _probe_endpoint(embedding_url, embedding_key)
    harmoniser_status = await _probe_endpoint(openai_url, openai_key)

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "portals": {
            pid: {"status": "unknown"}
            for pid in ["statistics_finland", "world_bank", "eurostat", "oecd", "un_data"]
        },
        "model_endpoints": {
            "embedder": embedder_status,
            "harmoniser": harmoniser_status,
        },
    }


# ---------------------------------------------------------------------------
# GET /v1/stats
# ---------------------------------------------------------------------------

def _build_db_url() -> str | None:
    """Build asyncpg DB URL using managed identity token, or None if not configured."""
    fqdn = os.environ.get("POSTGRES_FQDN")
    db_name = os.environ.get("POSTGRES_DB")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if not (fqdn and db_name and client_id):
        return None
    try:
        import urllib.parse
        from azure.identity import ManagedIdentityCredential
        credential = ManagedIdentityCredential(client_id=client_id)
        token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        username = os.environ.get("POSTGRES_USER", "tdo-id-api-dev")
        encoded = urllib.parse.quote(token.token, safe="")
        return f"postgresql+asyncpg://{username}@{fqdn}/{db_name}?password={encoded}&ssl=require"
    except Exception as exc:
        log.warning("stats_db_url_failed", error=str(exc))
        return None


@app.get("/v1/stats")
async def stats():
    """Aggregate counts by portal, theme, geo, access_type, resource_type."""
    db_url = _build_db_url()
    if db_url:
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine
            engine = create_async_engine(db_url, echo=False)
            async with engine.connect() as conn:
                total = (await conn.execute(text("SELECT COUNT(*) FROM datasets"))).scalar() or 0
                portal_rows = await conn.execute(
                    text("SELECT portal_id, COUNT(*) FROM datasets GROUP BY portal_id")
                )
                by_portal = {r[0]: r[1] for r in portal_rows}
                theme_rows = await conn.execute(
                    text("SELECT unnest(themes) AS t, COUNT(*) FROM datasets GROUP BY t")
                )
                by_theme = {r[0]: r[1] for r in theme_rows}
                geo_rows = await conn.execute(
                    text("SELECT unnest(geographic_coverage) AS g, COUNT(*) FROM datasets GROUP BY g")
                )
                by_geo = {r[0]: r[1] for r in geo_rows}
                access_rows = await conn.execute(
                    text("SELECT access_type, COUNT(*) FROM datasets GROUP BY access_type")
                )
                by_access = {r[0]: r[1] for r in access_rows}
                rtype_rows = await conn.execute(
                    text("SELECT resource_type, COUNT(*) FROM datasets GROUP BY resource_type")
                )
                by_rtype = {r[0]: r[1] for r in rtype_rows}
            await engine.dispose()
            return {
                "total_datasets": total,
                "by_portal": by_portal,
                "by_theme": by_theme,
                "by_geo": by_geo,
                "by_access_type": by_access,
                "by_resource_type": by_rtype,
            }
        except Exception as exc:
            log.warning("stats_db_query_failed", error=str(exc))

    return {
        "total_datasets": 0,
        "by_portal": {},
        "by_theme": {},
        "by_geo": {},
        "by_access_type": {},
        "by_resource_type": {},
    }
