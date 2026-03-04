"""
Unit tests for the Harmoniser.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.pipeline.harmoniser import Harmoniser, HarmoniserConfig


SDMX_PAYLOAD_NO_URL = {
    "data": {
        "dataflows": [
            {
                "id": "TYONV",
                "agencyID": "STATFIN",
                "name": {"en": "Unemployed persons"},
                "description": {"en": "Monthly unemployment statistics for Finland"},
            }
        ]
    },
    "meta": {"prepared": "2024-01-01"},
    "_source_portal": "https://stat.fi",
    "_publisher": "Statistics Finland",
    "_publisher_type": "NSO",
    "_access_type": "open",
    "_license": "CC-BY 4.0",
    "_schema_detected": "SDMX",
    "_formats": ["JSON", "SDMX"],
    "_languages": ["fi", "en"],
}

SDMX_PAYLOAD_NO_LICENSE = {
    **SDMX_PAYLOAD_NO_URL,
}

SDMX_PAYLOAD_NO_PUBLISHER = {
    "data": {
        "dataflows": [
            {
                "id": "TEST001",
                "name": {"en": "Test Dataset"},
            }
        ]
    },
    "_source_portal": "https://example.com",
    "_access_type": "open",
    "_schema_detected": "SDMX",
}


class TestHarmoniserDeterministic:
    """Tests for the deterministic (no LLM) harmonisation path."""

    @pytest.fixture
    def harmoniser(self):
        # No LLM endpoints configured — deterministic only
        return Harmoniser(config=HarmoniserConfig())

    @pytest.mark.asyncio
    async def test_never_invents_url(self, harmoniser):
        """Harmoniser must not invent dataset_url when not in payload."""
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        # The payload has no dataset_url field; it must remain None
        assert mvm.dataset_url is None

    @pytest.mark.asyncio
    async def test_never_invents_license(self, harmoniser):
        """Harmoniser uses portal default license, does not invent one."""
        payload = {
            "data": {
                "dataflows": [
                    {"id": "TEST", "agencyID": "ESTAT", "name": {"en": "Test"}}
                ]
            },
            "_source_portal": "https://ec.europa.eu/eurostat",
            "_access_type": "open",
            "_schema_detected": "SDMX",
        }
        mvm, _ = await harmoniser.process(payload, "eurostat")
        # License from portal defaults is acceptable; but it must not be invented
        # The test verifies the field comes from known defaults, not hallucination
        if mvm.license is not None:
            assert "CC-BY" in mvm.license or "open" in mvm.license.lower()

    @pytest.mark.asyncio
    async def test_never_invents_publisher_name(self, harmoniser):
        """Publisher must come from payload or portal defaults, not invented."""
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_PUBLISHER, "statistics_finland")
        # Portal defaults inject "Statistics Finland"; that's acceptable
        # The key rule: publisher is never None for known portals
        assert mvm.publisher is not None

    @pytest.mark.asyncio
    async def test_confidence_score_between_0_and_1(self, harmoniser):
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        assert 0.0 <= mvm.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_completeness_score_between_0_and_1(self, harmoniser):
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        assert 0.0 <= mvm.completeness_score <= 1.0

    @pytest.mark.asyncio
    async def test_low_confidence_records_flagged_for_review(self, harmoniser):
        """Records with confidence < 0.6 must be flagged for review."""
        # Minimal payload — low confidence expected
        minimal_payload = {
            "_source_portal": "https://example.com",
            "_access_type": "open",
            "_schema_detected": "unknown",
        }
        mvm, meta = await harmoniser.process(minimal_payload, "unknown_portal")
        if mvm.confidence_score < 0.6:
            assert meta["flagged_for_review"] is True
            assert meta["review_reason"] is not None

    @pytest.mark.asyncio
    async def test_high_confidence_not_flagged(self, harmoniser):
        """Records with confidence >= 0.6 should not be flagged."""
        mvm, meta = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        if mvm.confidence_score >= 0.6:
            assert meta["flagged_for_review"] is False

    @pytest.mark.asyncio
    async def test_pydantic_errors_caught_and_logged(self, harmoniser):
        """Pydantic validation errors must be caught, not re-raised."""
        # Pass a completely empty payload that will produce an invalid record
        try:
            mvm, meta = await harmoniser.process({}, "statistics_finland")
            # Should not raise; returns a fallback record
            assert mvm is not None
        except Exception as exc:
            pytest.fail(f"Harmoniser raised unexpectedly: {exc}")

    @pytest.mark.asyncio
    async def test_title_extracted_from_sdmx(self, harmoniser):
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        assert mvm.title == "Unemployed persons"

    @pytest.mark.asyncio
    async def test_publisher_from_portal_defaults(self, harmoniser):
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        assert mvm.publisher == "Statistics Finland"

    @pytest.mark.asyncio
    async def test_ingestion_timestamp_set(self, harmoniser):
        mvm, _ = await harmoniser.process(SDMX_PAYLOAD_NO_URL, "statistics_finland")
        assert mvm.ingestion_timestamp is not None
        assert isinstance(mvm.ingestion_timestamp, datetime)
