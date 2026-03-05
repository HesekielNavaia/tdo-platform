"""
Statistics Finland portal adapter.
Protocol: PxWeb REST JSON API
Base URL: https://pxdata.stat.fi:443/PxWeb/api/v1/en
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

STATFIN_BASE_URL = "https://pxdata.stat.fi:443/PxWeb/api/v1/en"


class StatisticsFinlandAdapter(BasePortalAdapter):
    portal_id = "statistics_finland"
    base_url = STATFIN_BASE_URL
    rate_limit_rps = 1.0
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["statistics_finland"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """
        Recursively traverse the PxWeb folder tree to discover all leaf datasets.
        The root URL returns databases (dbid/text), each database then yields
        folders (type l/h) and leaf tables (type t).
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Step 1: fetch top-level databases
            try:
                resp = await self._rate_limited_get(client, self.base_url)
                databases = resp.json()
            except Exception as e:
                log.error("statfin_root_error", error=str(e))
                return

            if not isinstance(databases, list):
                return

            for db in databases:
                db_id = db.get("dbid", "")
                if not db_id:
                    continue
                # Step 2: traverse each database
                async for record in self._traverse_node(client, db_id):
                    yield record

    async def _traverse_node(
        self, client: httpx.AsyncClient, path: str
    ) -> AsyncIterator[RawRecord]:
        """Recursively traverse a PxWeb catalogue node within a database."""
        url = f"{self.base_url}/{path}".rstrip("/")
        try:
            resp = await self._rate_limited_get(client, url)
            items = resp.json()
        except Exception as e:
            log.error("statfin_traverse_error", path=path, error=str(e))
            return

        if not isinstance(items, list):
            return

        for item in items:
            item_type = item.get("type", "")
            item_id = item.get("id", "")
            item_path = f"{path}/{item_id}".lstrip("/")

            if item_type in ("l", "h"):
                # Folder — recurse
                async for record in self._traverse_node(client, item_path):
                    yield record
            elif item_type == "t":
                # Table (leaf dataset) — fetch its metadata
                try:
                    record = await self.fetch_record(item_path)
                    yield record
                except Exception as e:
                    log.error("statfin_fetch_error", path=item_path, error=str(e))

    async def fetch_record(self, source_id: str) -> RawRecord:
        """
        Fetch metadata for a single PxWeb table.
        source_id is the path relative to the base URL.
        """
        url = f"{self.base_url}/{source_id.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(client, url)
            raw = resp.json()

        # Enrich with portal defaults and source path
        enriched = {
            **self.get_portal_defaults(),
            "pxweb_path": source_id,
            "pxweb_response": raw,
        }

        # Extract the key metadata fields from the PxWeb response
        if isinstance(raw, dict):
            enriched.update(raw)
        elif isinstance(raw, list) and raw:
            enriched.update(raw[0] if isinstance(raw[0], dict) else {})

        return self._make_record(source_id, enriched)
