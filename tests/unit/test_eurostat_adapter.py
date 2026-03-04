"""
Unit tests for the Eurostat adapter.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import respx
import httpx

from src.adapters.eurostat import EurostatAdapter, EUROSTAT_BASE_URL, EUROSTAT_DATAFLOW_URL

CASSETTE_DIR = Path(__file__).parent / "cassettes"


class TestEurostatAdapter:
    def test_instantiation(self):
        adapter = EurostatAdapter()
        assert adapter.portal_id == "eurostat"
        assert adapter.rate_limit_rps == 2.0
        assert adapter.adapter_type == "api"

    def test_get_portal_defaults(self):
        adapter = EurostatAdapter()
        defaults = adapter.get_portal_defaults()
        assert defaults["_publisher"] == "Eurostat"
        assert defaults["_publisher_type"] == "IO"

    @pytest.mark.asyncio
    async def test_fetch_catalogue_yields_records(self):
        adapter = EurostatAdapter()
        xml_data = (CASSETTE_DIR / "eurostat_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            respx.get(EUROSTAT_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) == 2
        for rec in records:
            assert rec.portal_id == "eurostat"
            assert rec.raw_payload_hash is not None
            assert len(rec.raw_payload_hash) == 64

    @pytest.mark.asyncio
    async def test_fetch_record_returns_record(self):
        adapter = EurostatAdapter()
        xml_data = (CASSETTE_DIR / "eurostat_dataflows.xml").read_bytes()

        with respx.mock:
            respx.get(f"{EUROSTAT_DATAFLOW_URL}/EMPLOYMENT_NACC").mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            record = await adapter.fetch_record("EMPLOYMENT_NACC")

        assert record.portal_id == "eurostat"
        assert record.raw_payload is not None
        assert record.raw_payload_hash is not None

    @pytest.mark.asyncio
    async def test_incremental_delta_uses_updated_after(self):
        adapter = EurostatAdapter()
        xml_data = (CASSETTE_DIR / "eurostat_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            route = respx.get(EUROSTAT_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue(updated_after="2024-01-01"):
                records.append(rec)

        # Verify the updatedAfter param was passed in the request
        assert route.called
        request = route.calls[0].request
        assert "updatedAfter" in str(request.url)

    def test_parse_sdmx_name_extracted(self):
        adapter = EurostatAdapter()
        xml_data = (CASSETTE_DIR / "eurostat_dataflows.xml").read_text()
        results = adapter._parse_sdmx_dataflows(xml_data)
        assert len(results) == 2
        names = [r["data"]["dataflows"][0]["name"]["en"] for r in results]
        assert "Employment by NACE activity" in names

    def test_parse_malformed_xml_returns_empty(self):
        adapter = EurostatAdapter()
        results = adapter._parse_sdmx_dataflows("<broken xml")
        assert results == []
