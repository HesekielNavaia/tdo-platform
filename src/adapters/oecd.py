"""
OECD portal adapter.
Protocol: SDMX REST 2.1
Base URL: https://sdmx.oecd.org/public/rest
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

OECD_BASE_URL = "https://sdmx.oecd.org/public/rest"
OECD_DATAFLOW_URL = f"{OECD_BASE_URL}/dataflow/OECD"

# Keywords indicating sub-national or experimental dataflows → resource_type="table"
SUBNATIONAL_INDICATORS = {
    "subnational", "regional", "experimental", "pilot",
    "test", "provisional", "beta",
}


class OECDAdapter(BasePortalAdapter):
    portal_id = "oecd"
    base_url = OECD_BASE_URL
    rate_limit_rps = 1.0
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["oecd"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """Fetch all OECD dataflows from SDMX catalogue."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(
                client,
                OECD_DATAFLOW_URL,
                params={"detail": "allstubs"},
                headers={"Accept": "application/xml"},
            )
            dataflows = self._parse_sdmx_dataflows(resp.text)
            for df in dataflows:
                enriched = {**self.get_portal_defaults(), **df}
                source_id = df.get("dataflow_id", "")
                if source_id:
                    yield self._make_record(source_id, enriched)

    async def fetch_record(self, source_id: str) -> RawRecord:
        """Fetch a single OECD dataflow by ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await self._rate_limited_get(
                client,
                f"{OECD_DATAFLOW_URL}/{source_id}",
                params={"detail": "full"},
                headers={"Accept": "application/xml"},
            )
            dataflows = self._parse_sdmx_dataflows(resp.text)
            raw = dataflows[0] if dataflows else {"dataflow_id": source_id}
            enriched = {**self.get_portal_defaults(), **raw}
            return self._make_record(source_id, enriched)

    def _is_subnational_or_experimental(self, df_id: str, name: str) -> bool:
        """Return True if this dataflow appears to be sub-national or experimental."""
        combined = (df_id + " " + name).lower()
        return any(k in combined for k in SUBNATIONAL_INDICATORS)

    def _parse_sdmx_dataflows(self, xml_text: str) -> list[dict[str, Any]]:
        """Parse SDMX 2.1 XML and extract OECD dataflow metadata."""
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
                agency_id = df.get("agencyID", "OECD")

                name_en = ""
                for name_el in df.findall(".//com:Name", ns):
                    lang = name_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if lang == "en" or not name_en:
                        name_en = name_el.text or ""
                        if lang == "en":
                            break

                desc_en = ""
                for desc_el in df.findall(".//com:Description", ns):
                    lang = desc_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if lang == "en" or not desc_en:
                        desc_en = desc_el.text or ""
                        if lang == "en":
                            break

                # Flag sub-national or experimental as resource_type="table"
                resource_type = "dataset"
                if self._is_subnational_or_experimental(df_id, name_en):
                    resource_type = "table"

                results.append({
                    "dataflow_id": df_id,
                    "agencyID": agency_id,
                    "resource_type": resource_type,
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
            log.error("oecd_xml_parse_error", error=str(e))

        return results
