"""
Statistics Finland portal adapter.
Protocol: PxWeb REST JSON API
Base URL: https://pxdata.stat.fi/PXWeb/api/v1/en
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

STATFIN_API_BASE  = "https://pxdata.stat.fi/PXWeb/api/v1/en"
STATFIN_BASE_URL  = f"{STATFIN_API_BASE}/StatFin"   # start traversal here
STATFIN_VIEW_BASE = "https://pxdata.stat.fi/PXWeb/pxweb/en/StatFin"


class StatisticsFinlandAdapter(BasePortalAdapter):
    portal_id = "statistics_finland"
    base_url = STATFIN_API_BASE
    rate_limit_rps = 0.5  # StatFin 429s at ~1 rps; 0.5 rps (2s gap) stays under their limit
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["statistics_finland"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """
        Recursively traverse the StatFin PxWeb folder tree starting at
        /StatFin, discovering all leaf table datasets.
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async for record in self._traverse_node(client, "StatFin"):
                yield record

    async def _traverse_node(
        self, client: httpx.AsyncClient, path: str
    ) -> AsyncIterator[RawRecord]:
        """Recursively traverse a PxWeb catalogue node."""
        url = f"{STATFIN_API_BASE}/{path}".rstrip("/")
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
        source_id is the path under /StatFin, e.g. "StatFin/matk/statfin_matk_pxt_117s.px"
        """
        url = f"{STATFIN_API_BASE}/{source_id.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(client, url)
            raw = resp.json()

        # The user-facing URL uses the pxweb viewer with double-underscore path format:
        # e.g. https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__matk/statfin_matk_pxt_117s.px
        # For nested databases: StatFin/Kokeelliset_tilastot/sbsis/table.px
        #   → /PxWeb/pxweb/en/Kokeelliset_tilastot/Kokeelliset_tilastot__sbsis/table.px
        viewer_path = source_id.lstrip("/").removeprefix("StatFin/")
        # viewer_path is now e.g. "matk/statfin_matk_pxt_117s.px"
        # or "Kokeelliset_tilastot/sbsis/table.px" for nested databases
        parts = viewer_path.split("/")
        if len(parts) == 2:
            # Standard StatFin table: {folder}/{table}.px
            db, subject, table = "StatFin", parts[0], parts[1]
        elif len(parts) >= 3:
            # Nested database: {database}/{folder}/{table}.px
            db, subject, table = parts[0], parts[1], "/".join(parts[2:])
        else:
            db, subject, table = "StatFin", "", viewer_path
        if subject:
            dataset_url = f"https://pxdata.stat.fi/PxWeb/pxweb/en/{db}/{db}__{subject}/{table}"
        else:
            dataset_url = f"https://pxdata.stat.fi/PxWeb/pxweb/en/{db}/{table}"
        enriched = {
            **self.get_portal_defaults(),
            "pxweb_path": source_id,
            "pxweb_response": raw,
            "_dataset_url": dataset_url,
            "url": dataset_url,
        }

        # Extract the key metadata fields from the PxWeb response
        if isinstance(raw, dict):
            enriched.update(raw)
        elif isinstance(raw, list) and raw:
            enriched.update(raw[0] if isinstance(raw[0], dict) else {})

        return self._make_record(source_id, enriched)
