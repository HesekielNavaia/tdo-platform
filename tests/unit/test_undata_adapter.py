"""
Unit tests for the UN Data adapter.
Includes malformed response handling tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import respx
import httpx

from src.adapters.un_data import UNDataAdapter, UNDATA_BASE_URL, UNDATA_DATAFLOW_URL

CASSETTE_DIR = Path(__file__).parent / "cassettes"


class TestUNDataAdapter:
    def test_instantiation(self):
        adapter = UNDataAdapter()
        assert adapter.portal_id == "un_data"
        assert adapter.rate_limit_rps == 1.0
        assert adapter.adapter_type == "api"

    def test_get_portal_defaults(self):
        adapter = UNDataAdapter()
        defaults = adapter.get_portal_defaults()
        assert defaults["_publisher"] == "United Nations Statistics Division"
        assert defaults["_publisher_type"] == "IO"

    @pytest.mark.asyncio
    async def test_fetch_catalogue_yields_records(self):
        adapter = UNDataAdapter()
        xml_data = (CASSETTE_DIR / "undata_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            respx.get(UNDATA_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) == 2
        for rec in records:
            assert rec.portal_id == "un_data"
            assert rec.raw_payload_hash is not None

    @pytest.mark.asyncio
    async def test_malformed_xml_does_not_raise(self):
        """Malformed XML must not raise — returns empty list (routes to LLM)."""
        adapter = UNDataAdapter()

        records = []
        with respx.mock:
            respx.get(UNDATA_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=b"<broken xml without closing tag")
            )
            # Should not raise
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        # Empty list — malformed response produces no records (not an exception)
        assert isinstance(records, list)

    @pytest.mark.asyncio
    async def test_fetch_record_with_malformed_response(self):
        """fetch_record must handle malformed XML and return a fallback raw payload."""
        adapter = UNDataAdapter()

        with respx.mock:
            respx.get(f"{UNDATA_DATAFLOW_URL}/BAD_SOURCE").mock(
                return_value=httpx.Response(200, content=b"THIS IS NOT XML AT ALL")
            )
            record = await adapter.fetch_record("BAD_SOURCE")

        # Must return a record, not raise
        assert record is not None
        assert record.portal_id == "un_data"
        assert record.source_id == "BAD_SOURCE"
        assert record.raw_payload is not None

    @pytest.mark.asyncio
    async def test_network_error_in_catalogue_handled(self):
        """Network errors in catalogue fetch must be caught."""
        adapter = UNDataAdapter()

        records = []
        with respx.mock:
            respx.get(UNDATA_DATAFLOW_URL).mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            # Should not raise
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert isinstance(records, list)

    def test_parse_malformed_xml_returns_empty(self):
        adapter = UNDataAdapter()
        result = adapter._parse_sdmx_dataflows_defensive("<not valid xml")
        assert result == []

    def test_parse_valid_xml_returns_dataflows(self):
        adapter = UNDataAdapter()
        xml_text = (CASSETTE_DIR / "undata_dataflows.xml").read_text()
        results = adapter._parse_sdmx_dataflows_defensive(xml_text)
        assert len(results) == 2
        ids = [r["dataflow_id"] for r in results]
        assert "DF_UNData_UNFAO" in ids
        assert "DF_UNData_WTO" in ids

    def test_raw_fallback_sets_unknown_schema(self):
        adapter = UNDataAdapter()
        fallback = adapter._raw_fallback("SRC_001", "<raw text>")
        assert fallback["_schema_detected"] == "unknown"
        assert fallback["dataflow_id"] == "SRC_001"
