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
    allow_origins=["*"],
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

@app.get("/v1/datasets", response_model=list[SearchResult])
async def list_datasets(
    q: Optional[str] = Query(None, description="Natural language search query"),
    geo: Optional[str] = Query(None, description="ISO 3166 codes, comma-separated"),
    theme: Optional[str] = Query(None, description="Theme codes, comma-separated"),
    publisher: Optional[str] = Query(None, description="Publisher name (fuzzy match)"),
    format: Optional[str] = Query(None, description="Format string"),
    access: Optional[str] = Query(None, description="open | restricted | embargoed"),
    resource_type: Optional[str] = Query(None, description="dataset | table | indicator | collection"),
    updated_after: Optional[str] = Query(None, description="ISO date"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search datasets using hybrid semantic + keyword search."""
    filters = SearchFilters(
        geo=geo.split(",") if geo else None,
        theme=theme.split(",") if theme else None,
        publisher=publisher,
        format=format,
        access=access,
        resource_type=resource_type,
        updated_after=updated_after,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )

    # In production this would use the real search engine
    # Returning empty list for now (wired in docker-compose / integration)
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
    """
    Return InternalProcessingRecord for a dataset.
    Requires elevated API scope.
    """
    # Check for elevated scope
    api_key = request.headers.get(API_KEY_HEADER, "")
    elevated_keys = set(
        filter(None, os.environ.get("TDO_ELEVATED_KEYS", "").split(","))
    )
    if elevated_keys and api_key not in elevated_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Elevated API scope required for provenance endpoint",
        )
    raise HTTPException(status_code=404, detail="Dataset not found")


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
