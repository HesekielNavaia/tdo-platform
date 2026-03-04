"""
Unit tests for the World Bank adapter.
Uses mocked HTTP responses.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
import httpx

from src.adapters.world_bank import WorldBankAdapter, WB_BASE_URL, WB_SOURCES_URL, WB_TOPICS_URL

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def load_cassette(name: str) -> dict | list:
    return json.loads((CASSETTE_DIR / name).read_text())


class TestWorldBankAdapter:
    def test_instantiation(self):
        adapter = WorldBankAdapter()
        assert adapter.portal_id == "world_bank"
        assert adapter.rate_limit_rps == 1.0
        assert adapter.adapter_type == "api"

    def test_get_portal_defaults(self):
        adapter = WorldBankAdapter()
        defaults = adapter.get_portal_defaults()
        assert defaults["_publisher"] == "World Bank"
        assert defaults["_publisher_type"] == "IO"
        assert defaults["_access_type"] == "open"

    @pytest.mark.asyncio
    async def test_fetch_catalogue_yields_records(self):
        adapter = WorldBankAdapter()
        sources = load_cassette("worldbank_sources.json")
        topics = load_cassette("worldbank_topics.json")

        records = []
        with respx.mock:
            respx.get(WB_TOPICS_URL).mock(return_value=httpx.Response(200, json=topics))
            respx.get(WB_SOURCES_URL).mock(return_value=httpx.Response(200, json=sources))
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) == 2
        for rec in records:
            assert rec.portal_id == "world_bank"
            assert rec.raw_payload is not None
            assert rec.raw_payload_hash is not None
            assert len(rec.raw_payload_hash) == 64

    @pytest.mark.asyncio
    async def test_fetch_record_returns_record(self):
        adapter = WorldBankAdapter()
        sources = load_cassette("worldbank_sources.json")
        single = [sources[0], [sources[1][0]]]

        with respx.mock:
            respx.get(f"{WB_SOURCES_URL}/2").mock(return_value=httpx.Response(200, json=single))
            record = await adapter.fetch_record("2")

        assert record.source_id == "2"
        assert record.portal_id == "world_bank"
        assert record.raw_payload is not None
        assert record.raw_payload_hash is not None

    @pytest.mark.asyncio
    async def test_topics_enrichment(self):
        adapter = WorldBankAdapter()
        sources = load_cassette("worldbank_sources.json")
        topics = load_cassette("worldbank_topics.json")

        records = []
        with respx.mock:
            respx.get(WB_TOPICS_URL).mock(return_value=httpx.Response(200, json=topics))
            respx.get(WB_SOURCES_URL).mock(return_value=httpx.Response(200, json=sources))
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) > 0
        first = records[0]
        assert "_topics" in first.raw_payload
        assert isinstance(first.raw_payload["_topics"], list)
        assert "Agriculture & Rural Development" in first.raw_payload["_topics"]
