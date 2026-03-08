"""
World Bank portal adapter.
Protocol: World Bank REST JSON
Base URL: https://api.worldbank.org/v2
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

WB_BASE_URL = "https://api.worldbank.org/v2"
WB_SOURCES_URL = f"{WB_BASE_URL}/sources"
WB_TOPICS_URL = f"{WB_BASE_URL}/topics"


class WorldBankAdapter(BasePortalAdapter):
    portal_id = "worldbank"
    base_url = WB_BASE_URL
    rate_limit_rps = 1.0
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["world_bank"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """
        Fetch all World Bank data sources with pagination.
        Enriches each source with topic keywords.
        """
        topics = await self._fetch_topics()
        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                resp = await self._rate_limited_get(
                    client,
                    WB_SOURCES_URL,
                    params={"format": "json", "per_page": 100, "page": page},
                )
                data = resp.json()
                # WB JSON: [ {page, pages, ...}, [ records ] ]
                if not isinstance(data, list) or len(data) < 2:
                    break

                meta = data[0]
                records = data[1]
                if not records:
                    break

                for source in records:
                    source_id = str(source.get("id", source.get("code", "")))
                    enriched = {
                        **self.get_portal_defaults(),
                        **source,
                        "_topics": topics,
                        "_dataset_url": f"https://databank.worldbank.org/source/{source_id}" if source_id else "",
                    }
                    yield self._make_record(source_id, enriched)

                total_pages = int(meta.get("pages", 1))
                if page >= total_pages:
                    break
                page += 1

    async def fetch_record(self, source_id: str) -> RawRecord:
        """Fetch a single World Bank data source by ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(
                client,
                f"{WB_SOURCES_URL}/{source_id}",
                params={"format": "json"},
            )
            data = resp.json()

        records = data[1] if isinstance(data, list) and len(data) >= 2 else []
        raw = records[0] if records else {}
        enriched = {**self.get_portal_defaults(), **raw}
        return self._make_record(source_id, enriched)

    async def _fetch_topics(self) -> list[str]:
        """Fetch all topic names for keyword enrichment."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await self._rate_limited_get(
                    client, WB_TOPICS_URL, params={"format": "json"}
                )
                data = resp.json()
            topics = data[1] if isinstance(data, list) and len(data) >= 2 else []
            return [t.get("value", "") for t in topics if t.get("value")]
        except Exception as e:
            log.warning("wb_topics_fetch_failed", error=str(e))
            return []
