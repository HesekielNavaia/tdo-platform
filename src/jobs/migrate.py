"""
Database migration job entry point for Azure Container Apps Job.
Runs 'alembic upgrade head' using managed identity PostgreSQL authentication.

Usage:
    JOB_NAME=migrate python -m src.jobs.migrate
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import urllib.parse

import structlog

log = structlog.get_logger(__name__)


def _get_sync_db_url() -> str:
    """Build a synchronous psycopg2 connection URL using a managed-identity token."""
    from azure.identity import ManagedIdentityCredential

    client_id = os.environ["AZURE_CLIENT_ID"]
    fqdn = os.environ["POSTGRES_FQDN"]
    db_name = os.environ["POSTGRES_DB"]

    credential = ManagedIdentityCredential(client_id=client_id)
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    username = os.environ.get("POSTGRES_USER", "tdo-id-harvest-dev")
    encoded_token = urllib.parse.quote(token.token, safe="")

    # Use psycopg2 driver for alembic (sync)
    return (
        f"postgresql+psycopg2://{username}@{fqdn}/{db_name}"
        f"?password={encoded_token}&sslmode=require"
    )


def main() -> None:
    log.info("migration_job_starting")

    try:
        db_url = _get_sync_db_url()
        log.info("db_url_built", fqdn=os.environ.get("POSTGRES_FQDN"))
    except Exception as exc:
        log.error("db_url_build_failed", error=str(exc))
        sys.exit(1)

    # Run alembic upgrade head
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("/app/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    try:
        command.upgrade(alembic_cfg, "head")
        log.info("migration_complete")
    except Exception as exc:
        log.error("migration_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
