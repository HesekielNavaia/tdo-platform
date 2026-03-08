"""
Embedding backfill job for Azure Container Apps Job.

Queries datasets with missing embedding_vec (optionally filtered by portal),
generates embeddings via the configured endpoint, and writes them back.

Usage:
    PORTAL_ID=statfin \\
    EMBEDDING_ENDPOINT=https://... \\
    EMBEDDING_API_KEY=... \\
    python -m src.jobs.embed
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import urllib.parse

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

log = structlog.get_logger(__name__)

BATCH_SIZE = 50  # records per embedding API call


def _get_db_url() -> str:
    from azure.identity import ManagedIdentityCredential

    client_id = os.environ["AZURE_CLIENT_ID"]
    fqdn = os.environ["POSTGRES_FQDN"]
    db_name = os.environ["POSTGRES_DB"]

    credential = ManagedIdentityCredential(client_id=client_id)
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    username = os.environ.get("POSTGRES_USER", "tdo-id-embed-dev")
    encoded_token = urllib.parse.quote(token.token, safe="")

    return (
        f"postgresql+asyncpg://{username}@{fqdn}/{db_name}"
        f"?password={encoded_token}&ssl=require"
    )


def _get_kv_secret(secret_name: str) -> str | None:
    try:
        from azure.identity import ManagedIdentityCredential
        from azure.keyvault.secrets import SecretClient

        client_id = os.environ["AZURE_CLIENT_ID"]
        kv_uri = os.environ["KEYVAULT_URI"]
        credential = ManagedIdentityCredential(client_id=client_id)
        client = SecretClient(vault_url=kv_uri, credential=credential)
        return client.get_secret(secret_name).value
    except Exception as exc:
        log.warning("kv_secret_fetch_failed", secret=secret_name, error=str(exc))
        return None


def _build_text(row: dict) -> str:
    parts = [
        row.get("title") or "",
        row.get("description") or "",
        " ".join(row.get("keywords") or []),
        " ".join(row.get("themes") or []),
        " ".join(row.get("geographic_coverage") or []),
        row.get("publisher") or "",
    ]
    return " ".join(p for p in parts if p).strip()


async def _embed_batch(
    texts: list[str], endpoint: str, api_key: str | None
) -> list[list[float]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    endpoint,
                    json={"input": texts, "model": "Cohere-embed-v3-multilingual"},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                if "data" in data:
                    return [item["embedding"] for item in data["data"]]
                if isinstance(data, list):
                    return data
                raise RuntimeError(f"Unexpected response format: {list(data.keys())}")
        except Exception as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            log.warning("embed_retry", attempt=attempt + 1, error=str(exc), wait=wait)
            await asyncio.sleep(wait)
    return []


async def main() -> None:
    portal_id = os.environ.get("PORTAL_ID", "").strip() or None

    # ── Embedding endpoint config ─────────────────────────────────────────────
    # Prefer direct env vars; fall back to Key Vault secrets.
    endpoint = (
        os.environ.get("EMBEDDING_ENDPOINT")
        or os.environ.get("EMBEDDER_ENDPOINT")
        or _get_kv_secret("embedder-endpoint")
    )
    api_key = (
        os.environ.get("EMBEDDING_API_KEY")
        or os.environ.get("EMBEDDER_KEY")
        or _get_kv_secret("embedder-key")
    )

    if not endpoint:
        log.error("missing_embedding_endpoint")
        sys.exit(1)

    # Cohere serverless endpoints need /v1/embeddings appended
    if not endpoint.rstrip("/").endswith(("/v1/embeddings", "/score")):
        endpoint = endpoint.rstrip("/") + "/v1/embeddings"

    log.info("embed_job_starting", portal_id=portal_id or "all", endpoint=endpoint[:60])

    # ── DB connection ─────────────────────────────────────────────────────────
    try:
        db_url = _get_db_url()
    except Exception as exc:
        log.error("db_url_failed", error=str(exc))
        sys.exit(1)

    engine = create_async_engine(db_url, echo=False)

    # ── Query records missing embeddings ─────────────────────────────────────
    where = "embedding_vec IS NULL"
    params: dict = {}
    if portal_id:
        where += " AND portal_id = :portal_id"
        params["portal_id"] = portal_id

    async with engine.connect() as conn:
        count_row = await conn.execute(
            text(f"SELECT COUNT(*) FROM datasets WHERE {where}"), params
        )
        total_missing = count_row.scalar() or 0

    log.info("records_to_embed", total=total_missing, portal=portal_id or "all")

    if total_missing == 0:
        log.info("nothing_to_do")
        await engine.dispose()
        return

    # ── Process in batches ────────────────────────────────────────────────────
    processed = 0
    errors = 0
    offset = 0

    while True:
        async with engine.connect() as conn:
            rows = (await conn.execute(
                text(f"""
                    SELECT id, title, description, keywords, themes,
                           geographic_coverage, publisher
                    FROM datasets
                    WHERE {where}
                    ORDER BY ingestion_timestamp DESC
                    LIMIT :lim OFFSET :off
                """),
                {**params, "lim": BATCH_SIZE, "off": offset},
            )).mappings().fetchall()

        if not rows:
            break

        texts = [_build_text(dict(r)) for r in rows]
        ids = [str(r["id"]) for r in rows]

        try:
            embeddings = await _embed_batch(texts, endpoint, api_key)
        except Exception as exc:
            log.error("batch_embed_failed", offset=offset, error=str(exc))
            errors += len(rows)
            offset += BATCH_SIZE
            continue

        # Write embeddings back
        async with engine.begin() as conn:
            for row_id, emb in zip(ids, embeddings):
                vec_str = "[" + ",".join(str(x) for x in emb) + "]"
                await conn.execute(
                    text("""
                        UPDATE datasets
                        SET embedding = :emb_json,
                            embedding_vec = CAST(:vec AS vector)
                        WHERE id = CAST(:id AS uuid)
                    """),
                    {
                        "emb_json": json.dumps(emb),
                        "vec": vec_str,
                        "id": row_id,
                    },
                )

        processed += len(ids)
        log.info(
            "batch_complete",
            processed=processed,
            total=total_missing,
            errors=errors,
            pct=round(processed / total_missing * 100, 1),
        )
        offset += BATCH_SIZE

    await engine.dispose()
    log.info("embed_job_done", processed=processed, errors=errors)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
