"""
Unit tests for the OECD adapter.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import respx
import httpx

from src.adapters.oecd import OECDAdapter, OECD_BASE_URL, OECD_DATAFLOW_URL

CASSETTE_DIR = Path(__file__).parent / "cassettes"


class TestOECDAdapter:
    def test_instantiation(self):
        adapter = OECDAdapter()
        assert adapter.portal_id == "oecd"
        assert adapter.rate_limit_rps == 1.0
        assert adapter.adapter_type == "api"

    def test_get_portal_defaults(self):
        adapter = OECDAdapter()
        defaults = adapter.get_portal_defaults()
        assert defaults["_publisher"] == "OECD"
        assert defaults["_publisher_type"] == "IO"

    @pytest.mark.asyncio
    async def test_fetch_catalogue_yields_records(self):
        adapter = OECDAdapter()
        xml_data = (CASSETTE_DIR / "oecd_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            respx.get(OECD_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) == 2
        for rec in records:
            assert rec.portal_id == "oecd"
            assert rec.raw_payload_hash is not None

    @pytest.mark.asyncio
    async def test_subnational_flagged_as_table(self):
        adapter = OECDAdapter()
        xml_data = (CASSETTE_DIR / "oecd_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            respx.get(OECD_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        # "REGIONAL_PILOT" contains "regional" and "pilot" → should be "table"
        regional = next(r for r in records if "REGIONAL_PILOT" in r.source_id)
        assert regional.raw_payload.get("resource_type") == "table"

    @pytest.mark.asyncio
    async def test_regular_dataset_is_dataset_type(self):
        adapter = OECDAdapter()
        xml_data = (CASSETTE_DIR / "oecd_dataflows.xml").read_bytes()

        records = []
        with respx.mock:
            respx.get(OECD_DATAFLOW_URL).mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        employment = next(r for r in records if r.source_id == "EMPLOYMENT")
        assert employment.raw_payload.get("resource_type") == "dataset"

    def test_is_subnational_detection(self):
        adapter = OECDAdapter()
        assert adapter._is_subnational_or_experimental("REGIONAL_DATA", "Regional Data") is True
        assert adapter._is_subnational_or_experimental("PILOT_001", "Pilot dataset") is True
        assert adapter._is_subnational_or_experimental("EMPLOYMENT", "Employment") is False

    @pytest.mark.asyncio
    async def test_fetch_record_returns_record(self):
        adapter = OECDAdapter()
        xml_data = (CASSETTE_DIR / "oecd_dataflows.xml").read_bytes()

        with respx.mock:
            respx.get(f"{OECD_DATAFLOW_URL}/EMPLOYMENT").mock(
                return_value=httpx.Response(200, content=xml_data)
            )
            record = await adapter.fetch_record("EMPLOYMENT")

        assert record.portal_id == "oecd"
        assert record.raw_payload is not None
        assert record.raw_payload_hash is not None
