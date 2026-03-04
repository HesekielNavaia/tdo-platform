"""
Eurostat portal adapter.
Protocol: SDMX REST 2.1
Base URL: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

EUROSTAT_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"
EUROSTAT_DATAFLOW_URL = f"{EUROSTAT_BASE_URL}/dataflow/ESTAT"


class EurostatAdapter(BasePortalAdapter):
    portal_id = "eurostat"
    base_url = EUROSTAT_BASE_URL
    rate_limit_rps = 2.0
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["eurostat"]

    async def fetch_catalogue(
        self, updated_after: str | None = None
    ) -> AsyncIterator[RawRecord]:
        """
        Fetch all Eurostat dataflows.
        Uses updatedAfter for incremental delta harvesting.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            params: dict[str, str] = {"detail": "allstubs"}
            if updated_after:
                params["updatedAfter"] = updated_after

            resp = await self._rate_limited_get(
                client, EUROSTAT_DATAFLOW_URL, params=params,
                headers={"Accept": "application/xml"}
            )

            dataflows = self._parse_sdmx_dataflows(resp.text)
            for df in dataflows:
                enriched = {**self.get_portal_defaults(), **df}
                source_id = df.get("dataflow_id", "")
                if source_id:
                    yield self._make_record(source_id, enriched)

    async def fetch_record(self, source_id: str) -> RawRecord:
        """Fetch a single Eurostat dataflow by ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(
                client,
                f"{EUROSTAT_DATAFLOW_URL}/{source_id}",
                params={"detail": "full"},
                headers={"Accept": "application/xml"},
            )
            dataflows = self._parse_sdmx_dataflows(resp.text)
            raw = dataflows[0] if dataflows else {"dataflow_id": source_id}
            enriched = {**self.get_portal_defaults(), **raw}
            return self._make_record(source_id, enriched)

    def _parse_sdmx_dataflows(self, xml_text: str) -> list[dict[str, Any]]:
        """
        Parse SDMX 2.1 Structure Message XML and extract dataflow metadata.
        Returns a list of dicts matching expected MVM fields.
        """
        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
                "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
                "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
            }

            dataflows = root.findall(".//str:Dataflow", ns)
            for df in dataflows:
                df_id = df.get("id", "")
                agency_id = df.get("agencyID", "ESTAT")

                # Extract English name
                name_en = ""
                for name_el in df.findall(".//com:Name", ns):
                    lang = name_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if lang == "en" or not name_en:
                        name_en = name_el.text or ""
                        if lang == "en":
                            break

                # Extract English description
                desc_en = ""
                for desc_el in df.findall(".//com:Description", ns):
                    lang = desc_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if lang == "en" or not desc_en:
                        desc_en = desc_el.text or ""
                        if lang == "en":
                            break

                results.append({
                    "dataflow_id": df_id,
                    "agencyID": agency_id,
                    "data": {
                        "dataflows": [{
                            "id": df_id,
                            "agencyID": agency_id,
                            "name": {"en": name_en},
                            "description": {"en": desc_en} if desc_en else {},
                        }]
                    },
                })
        except ET.ParseError as e:
            log.error("eurostat_xml_parse_error", error=str(e))

        return results
