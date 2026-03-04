"""
Unit tests for the Statistics Finland adapter.
Uses mocked HTTP responses (no real API calls).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
import httpx

from src.adapters.statistics_finland import StatisticsFinlandAdapter, STATFIN_BASE_URL

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def load_cassette(name: str) -> dict | list:
    return json.loads((CASSETTE_DIR / name).read_text())


class TestStatisticsFinlandAdapter:
    def test_instantiation(self):
        adapter = StatisticsFinlandAdapter()
        assert adapter.portal_id == "statistics_finland"
        assert adapter.rate_limit_rps == 1.0
        assert adapter.adapter_type == "api"

    def test_get_portal_defaults(self):
        adapter = StatisticsFinlandAdapter()
        defaults = adapter.get_portal_defaults()
        assert defaults["_publisher"] == "Statistics Finland"
        assert defaults["_publisher_type"] == "NSO"
        assert defaults["_access_type"] == "open"
        assert "_source_portal" in defaults

    @pytest.mark.asyncio
    async def test_fetch_record_returns_raw_record(self):
        adapter = StatisticsFinlandAdapter()
        cassette_data = load_cassette("statfin_record.json")
        source_id = "StatFin/tym/tyonv/"

        with respx.mock:
            respx.get(f"{STATFIN_BASE_URL}/{source_id}").mock(
                return_value=httpx.Response(200, json=cassette_data)
            )
            record = await adapter.fetch_record(source_id)

        assert record.raw_payload is not None
        assert isinstance(record.raw_payload, dict)
        assert record.raw_payload_hash is not None
        assert len(record.raw_payload_hash) == 64  # SHA-256
        assert record.source_id == source_id
        assert record.portal_id == "statistics_finland"

    @pytest.mark.asyncio
    async def test_fetch_record_hash_is_sha256(self):
        adapter = StatisticsFinlandAdapter()
        cassette_data = load_cassette("statfin_record.json")
        source_id = "StatFin/tym/tyonv/"

        with respx.mock:
            respx.get(f"{STATFIN_BASE_URL}/{source_id}").mock(
                return_value=httpx.Response(200, json=cassette_data)
            )
            record = await adapter.fetch_record(source_id)

        # Verify hash format is SHA-256 (64 hex chars)
        assert all(c in "0123456789abcdef" for c in record.raw_payload_hash)

    @pytest.mark.asyncio
    async def test_fetch_record_source_id_is_set(self):
        adapter = StatisticsFinlandAdapter()
        cassette_data = load_cassette("statfin_record.json")
        source_id = "StatFin/vrm/010/"

        with respx.mock:
            respx.get(f"{STATFIN_BASE_URL}/{source_id}").mock(
                return_value=httpx.Response(200, json=cassette_data)
            )
            record = await adapter.fetch_record(source_id)

        assert record.source_id == source_id

    @pytest.mark.asyncio
    async def test_fetch_catalogue_yields_records(self):
        adapter = StatisticsFinlandAdapter()
        catalogue = load_cassette("statfin_catalogue.json")
        record_data = load_cassette("statfin_record.json")

        records = []
        with respx.mock:
            # Root catalogue
            respx.get(STATFIN_BASE_URL).mock(
                return_value=httpx.Response(200, json=catalogue)
            )
            # Sub-folder responses — return leaf tables
            respx.get(f"{STATFIN_BASE_URL}/tym").mock(
                return_value=httpx.Response(200, json=[
                    {"id": "tyonv", "text": "Unemployed", "type": "t", "updated": "2024-01-01"}
                ])
            )
            respx.get(f"{STATFIN_BASE_URL}/vrm").mock(
                return_value=httpx.Response(200, json=[
                    {"id": "vrm_01", "text": "Population", "type": "t", "updated": "2024-01-01"}
                ])
            )
            # Leaf table metadata
            respx.get(f"{STATFIN_BASE_URL}/tym/tyonv").mock(
                return_value=httpx.Response(200, json=record_data)
            )
            respx.get(f"{STATFIN_BASE_URL}/vrm/vrm_01").mock(
                return_value=httpx.Response(200, json=record_data)
            )
            async for rec in adapter.fetch_catalogue():
                records.append(rec)

        assert len(records) >= 1
        for rec in records:
            assert rec.portal_id == "statistics_finland"
            assert rec.raw_payload is not None
            assert rec.raw_payload_hash is not None
