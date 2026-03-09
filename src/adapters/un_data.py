"""
UN Data portal adapter.
Protocol: SDMX (partial compliance)
Base URL: http://data.un.org/ws/rest
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, AsyncIterator

import httpx
import structlog

from src.adapters.base import BasePortalAdapter, RawRecord
from src.pipeline.mapping_tables import PORTAL_DEFAULTS

log = structlog.get_logger(__name__)

UNDATA_BASE_URL = "http://data.un.org/ws/rest"
UNDATA_DATAFLOW_URL = f"{UNDATA_BASE_URL}/dataflow/all"
UNSTATS_SDG_URL = "https://unstats.un.org/SDGAPI/v1/sdg/Series/List"


class UNDataAdapter(BasePortalAdapter):
    portal_id = "un_data"
    base_url = UNDATA_BASE_URL
    rate_limit_rps = 1.0
    adapter_type = "api"

    def get_portal_defaults(self) -> dict[str, Any]:
        return PORTAL_DEFAULTS["un_data"]

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """
        Fetch UN Data records from two sources:
        1. All SDMX dataflows across all UN Data agencies.
        2. UN Stats SDG indicator series (unstats.un.org/SDGAPI).
        """
        seen: set[str] = set()

        # --- Source 1: SDMX dataflows (all agencies) ---
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            try:
                resp = await self._rate_limited_get(
                    client,
                    UNDATA_DATAFLOW_URL,
                    params={"detail": "allstubs"},
                    headers={"Accept": "application/xml"},
                )
                dataflows = self._parse_sdmx_dataflows_defensive(resp.text)
            except Exception as e:
                log.error("undata_catalogue_fetch_failed", error=str(e))
                dataflows = []

            for df in dataflows:
                source_id = df.get("dataflow_id", "")
                if source_id and source_id not in seen:
                    seen.add(source_id)
                    enriched = {**self.get_portal_defaults(), **df}
                    yield self._make_record(source_id, enriched)

        # --- Source 2: UN Stats SDG series ---
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.get(UNSTATS_SDG_URL, timeout=30.0)
                resp.raise_for_status()
                series_list = resp.json()
            except Exception as e:
                log.error("unstats_sdg_fetch_failed", error=str(e))
                series_list = []

            for series in series_list:
                code = series.get("code", "")
                if not code or code in seen:
                    continue
                seen.add(code)
                description = series.get("description", code)
                goals = series.get("goal", [])
                indicators = series.get("indicator", [])
                theme = f"SDG {goals[0]}" if goals else "SDG"
                enriched = {
                    **self.get_portal_defaults(),
                    "dataflow_id": code,
                    "agencyID": "IAEG-SDGs",
                    "_dataset_url": f"https://unstats.un.org/sdgs/indicators/database/?indicator={indicators[0]}" if indicators else f"https://unstats.un.org/sdgs/",
                    "data": {
                        "dataflows": [{
                            "id": code,
                            "agencyID": "IAEG-SDGs",
                            "name": {"en": description},
                            "description": {"en": f"SDG indicator series. Goals: {', '.join(goals)}. Indicators: {', '.join(indicators)}."},
                        }]
                    },
                }
                yield self._make_record(f"SDG_{code}", enriched)

    async def fetch_record(self, source_id: str) -> RawRecord:
        """Fetch a single UN Data dataflow. On parse failure, returns raw text payload."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await self._rate_limited_get(
                    client,
                    f"{UNDATA_DATAFLOW_URL}/{source_id}",
                    params={"detail": "full"},
                    headers={"Accept": "application/xml"},
                )
                dataflows = self._parse_sdmx_dataflows_defensive(resp.text)
                if dataflows:
                    raw = dataflows[0]
                else:
                    # Parse failure — store raw text for LLM
                    raw = self._raw_fallback(source_id, resp.text)
            except Exception as e:
                log.error("undata_fetch_record_failed", source_id=source_id, error=str(e))
                raw = self._raw_fallback(source_id, "")

        enriched = {**self.get_portal_defaults(), **raw}
        return self._make_record(source_id, enriched)

    def _raw_fallback(self, source_id: str, raw_text: str) -> dict[str, Any]:
        """Create a minimal dict for LLM processing when parsing fails."""
        return {
            "dataflow_id": source_id,
            "_schema_detected": "unknown",
            "_raw_text": raw_text[:4000],  # Truncate for safety
        }

    def _parse_sdmx_dataflows_defensive(self, xml_text: str) -> list[dict[str, Any]]:
        """
        Parse SDMX 2.1 XML with aggressive error handling.
        Any parse failure logs the error and routes to unknown schema.
        """
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.warning(
                "undata_xml_parse_failure",
                error=str(e),
                payload_preview=xml_text[:200],
            )
            return []

        # Try multiple namespace configurations (UN Data has inconsistent compliance)
        ns_variants = [
            {
                "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
                "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
                "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
            },
            {},  # No-namespace fallback
        ]

        for ns in ns_variants:
            try:
                if ns:
                    dataflows = root.findall(".//str:Dataflow", ns)
                else:
                    dataflows = root.findall(".//{*}Dataflow")

                if not dataflows:
                    continue

                for df in dataflows:
                    df_id = df.get("id", "")
                    agency_id = df.get("agencyID", "UNSD")

                    name_en = self._extract_text_defensive(df, ns, "Name")
                    desc_en = self._extract_text_defensive(df, ns, "Description")

                    results.append({
                        "dataflow_id": df_id,
                        "agencyID": agency_id,
                        "_dataset_url": f"https://data.un.org/Data.aspx?d={agency_id}&f=series%3A{df_id}" if agency_id == "UNSD" else f"https://data.un.org/Data.aspx?d={agency_id}",
                        "data": {
                            "dataflows": [{
                                "id": df_id,
                                "agencyID": agency_id,
                                "name": {"en": name_en},
                                "description": {"en": desc_en} if desc_en else {},
                            }]
                        },
                    })

                if results:
                    break

            except Exception as e:
                log.warning("undata_parse_variant_failed", error=str(e))
                continue

        return results

    def _extract_text_defensive(
        self, element: ET.Element, ns: dict, tag: str
    ) -> str:
        """Safely extract text from an XML element, with fallback to empty string."""
        try:
            if ns:
                com_ns = ns.get("com", "")
                tag_path = f".//{{{com_ns}}}{tag}" if com_ns else f".//{tag}"
            else:
                tag_path = f".//{{{tag}}}" if tag else ".//{*}" + tag

            # Try with common namespace
            com_prefix = "com" if ns else None
            if com_prefix:
                for el in element.findall(f".//{com_prefix}:{tag}", ns):
                    lang = el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if el.text and (lang == "en" or not el.text.strip()):
                        return el.text.strip() or ""
                    elif el.text:
                        return el.text.strip()

            # Wildcard fallback
            for el in element.findall(f".//*"):
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == tag and el.text:
                    return el.text.strip()
        except Exception:
            pass
        return ""
