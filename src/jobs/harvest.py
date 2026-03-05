"""
Harvest job entry point for Azure Container Apps Job.

Reads PORTAL_ID env var, connects to PostgreSQL via managed identity token,
fetches secrets from Key Vault, then runs harvest → harmonise → embed → index
pipeline via the orchestrator.

Usage (set env vars before running):
    PORTAL_ID=statfin python -m src.jobs.harvest
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import urllib.parse

import structlog

log = structlog.get_logger(__name__)

# Map short / user-friendly portal names to internal adapter IDs
PORTAL_MAP: dict[str, str] = {
    "statfin": "statistics_finland",
    "statistics_finland": "statistics_finland",
    "eurostat": "eurostat",
    "worldbank": "world_bank",
    "world_bank": "world_bank",
    "oecd": "oecd",
    "undata": "un_data",
    "un_data": "un_data",
}


def _get_db_url() -> str:
    """Build asyncpg connection URL using a managed-identity access token."""
    from azure.identity import ManagedIdentityCredential

    client_id = os.environ["AZURE_CLIENT_ID"]
    fqdn = os.environ["POSTGRES_FQDN"]
    db_name = os.environ["POSTGRES_DB"]

    credential = ManagedIdentityCredential(client_id=client_id)
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    # Username = the managed identity display name as registered in PostgreSQL
    username = os.environ.get("POSTGRES_USER", "tdo-id-harvest-dev")
    encoded_token = urllib.parse.quote(token.token, safe="")

    return (
        f"postgresql+asyncpg://{username}@{fqdn}/{db_name}"
        f"?password={encoded_token}&ssl=require"
    )


def _get_kv_secret(secret_name: str) -> str | None:
    """Retrieve a secret from Azure Key Vault using the managed identity."""
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


async def main() -> None:
    portal_short = os.environ.get("PORTAL_ID", "").lower().strip()
    portal_id = PORTAL_MAP.get(portal_short, portal_short)

    if not portal_id:
        log.error("missing_portal_id", msg="Set PORTAL_ID env var (e.g. statfin, eurostat)")
        sys.exit(1)

    log.info("harvest_job_starting", portal_id=portal_id)

    # ── Database connection ───────────────────────────────────────────────────
    try:
        db_url = _get_db_url()
        log.info("db_url_built", fqdn=os.environ.get("POSTGRES_FQDN"))
    except Exception as exc:
        log.error("db_url_build_failed", error=str(exc))
        sys.exit(1)

    # ── Model endpoint config from Key Vault ──────────────────────────────────
    openai_endpoint = _get_kv_secret("openai-endpoint")
    openai_key = _get_kv_secret("openai-key")
    embedder_endpoint = _get_kv_secret("embedder-endpoint")
    embedder_key = _get_kv_secret("embedder-key")

    harmoniser_config: dict | None = None
    if openai_endpoint:
        harmoniser_config = {
            "openai_endpoint": openai_endpoint,
            "openai_api_key": openai_key,
        }
        log.info("harmoniser_configured", endpoint=openai_endpoint[:40] + "...")

    embedder_config: dict | None = None
    if embedder_endpoint:
        embedder_config = {
            "endpoint_url": embedder_endpoint,
            "api_key": embedder_key,
        }
        log.info("embedder_configured", endpoint=embedder_endpoint[:40] + "...")

    # ── Run pipeline ──────────────────────────────────────────────────────────
    from src.orchestrator.functions import tdo_pipeline_orchestrator

    try:
        result = await tdo_pipeline_orchestrator(
            portal_ids=[portal_id],
            db_url=db_url,
            harmoniser_config=harmoniser_config,
            embedder_config=embedder_config,
        )
    except Exception as exc:
        log.error("pipeline_failed", error=str(exc))
        sys.exit(1)

    log.info(
        "harvest_job_complete",
        run_id=result.get("run_id"),
        total_indexed=result.get("total_indexed", 0),
        error_count=len(result.get("errors", [])),
    )

    if result.get("errors"):
        for err in result["errors"]:
            log.warning("pipeline_error", **err)
        # Exit 1 so the Container App Job marks this execution as failed
        # and retries (up to replicaRetryLimit).
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
