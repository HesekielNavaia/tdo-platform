"""
Unit tests for the orchestrator functions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.functions import (
    harmonise_record,
    embed_record,
    index_record,
    tdo_pipeline_orchestrator,
    _get_adapter,
)
from src.models.mvm import MVMRecord

VALID_MVM_DICT = {
    "id": "test-uuid-orch-001",
    "source_id": "src-orch-001",
    "title": "Test Dataset",
    "publisher": "Statistics Finland",
    "publisher_type": "NSO",
    "source_portal": "statistics_finland",
    "access_type": "open",
    "metadata_standard": "SDMX",
    "confidence_score": 0.85,
    "completeness_score": 0.75,
    "freshness_score": 0.9,
    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
    "source_id_aliases": [],
    "keywords": [],
    "themes": [],
    "geographic_coverage": [],
    "languages": [],
    "formats": [],
}

RAW_RECORD = {
    "source_id": "src-orch-001",
    "portal_id": "statistics_finland",
    "raw_payload": {
        "_source_portal": "https://stat.fi",
        "_publisher": "Statistics Finland",
        "_publisher_type": "NSO",
        "_access_type": "open",
        "_schema_detected": "SDMX",
        "data": {
            "dataflows": [{
                "id": "TYONV",
                "agencyID": "STATFIN",
                "name": {"en": "Unemployed persons"},
            }]
        },
    },
    "raw_payload_hash": "abc123",
    "fetched_at": datetime.now(timezone.utc).isoformat(),
}


class TestActivityFunctions:
    @pytest.mark.asyncio
    async def test_harmonise_record_returns_mvm(self):
        """harmonise_record must return an MVM dict."""
        result = await harmonise_record(
            raw_record=RAW_RECORD,
            portal_id="statistics_finland",
            run_id="test-run-001",
        )
        assert "mvm" in result
        assert "processing_meta" in result
        mvm = result["mvm"]
        assert "title" in mvm
        assert mvm["title"] is not None

    @pytest.mark.asyncio
    async def test_embed_record_calls_embedder(self):
        """embed_record must call the embedder and return embedding."""
        mock_embedding = [0.1] * 1024

        with patch("src.pipeline.embedder.Embedder") as MockEmbedder:
            mock_inst = AsyncMock()
            mock_inst.embed = AsyncMock(return_value=mock_embedding)
            MockEmbedder.return_value = mock_inst

            result = await embed_record(
                mvm_dict=VALID_MVM_DICT,
                run_id="test-run-001",
                portal_id="statistics_finland",
                embedder_config={
                    "endpoint_url": "http://embeddings:80",
                    "expected_dim": 1024,
                },
            )

        assert "embedding" in result
        assert len(result["embedding"]) == 1024

    @pytest.mark.asyncio
    async def test_index_record_skips_without_db_url(self):
        """index_record should skip (not raise) when no db_url is provided."""
        result = await index_record(
            mvm_dict=VALID_MVM_DICT,
            embedding=[0.1] * 1024,
            run_id="test-run-001",
            portal_id="statistics_finland",
            db_url=None,
        )
        assert "dataset_id" in result

    @pytest.mark.asyncio
    async def test_pipeline_orchestrator_structure(self):
        """Orchestrator must return run_id, total_indexed, errors."""
        # Mock all activity functions to avoid real HTTP/DB calls
        with patch("src.orchestrator.functions.harvest_portal") as mock_harvest:
            mock_harvest.return_value = {"records": [], "run_id": "r1", "portal_id": "p1"}
            result = await tdo_pipeline_orchestrator(
                portal_ids=["statistics_finland"],
                db_url=None,
            )

        assert "run_id" in result
        assert "total_indexed" in result
        assert "errors" in result


class TestGetAdapter:
    def test_get_adapter_statistics_finland(self):
        adapter = _get_adapter("statistics_finland")
        assert adapter.portal_id == "statistics_finland"

    def test_get_adapter_world_bank(self):
        adapter = _get_adapter("world_bank")
        assert adapter.portal_id == "world_bank"

    def test_get_adapter_eurostat(self):
        adapter = _get_adapter("eurostat")
        assert adapter.portal_id == "eurostat"

    def test_get_adapter_oecd(self):
        adapter = _get_adapter("oecd")
        assert adapter.portal_id == "oecd"

    def test_get_adapter_un_data(self):
        adapter = _get_adapter("un_data")
        assert adapter.portal_id == "un_data"

    def test_get_adapter_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown portal_id"):
            _get_adapter("nonexistent_portal")


class TestHarvestPortal:
    @pytest.mark.asyncio
    async def test_harvest_portal_returns_records(self):
        from src.orchestrator.functions import harvest_portal
        from src.adapters.base import RawRecord
        from datetime import datetime, timezone
        import hashlib, json

        fake_payload = {"id": "T1", "name": "Test"}
        fake_hash    = hashlib.sha256(json.dumps(fake_payload).encode()).hexdigest()
        fake_record  = RawRecord(
            source_id="T1",
            portal_id="statistics_finland",
            raw_payload=fake_payload,
            raw_payload_hash=fake_hash,
            adapter_type="api",
            fetched_at=datetime.now(timezone.utc),
        )

        async def fake_catalogue():
            yield fake_record

        mock_adapter = MagicMock()
        mock_adapter.fetch_catalogue = fake_catalogue

        with patch("src.orchestrator.functions._get_adapter", return_value=mock_adapter):
            result = await harvest_portal(
                portal_id="statistics_finland",
                run_id="run-001",
                db_url=None,
            )

        assert "records" in result
        assert len(result["records"]) == 1
        assert result["records"][0]["source_id"] == "T1"

    @pytest.mark.asyncio
    async def test_harvest_portal_failure_raises(self):
        from src.orchestrator.functions import harvest_portal

        mock_adapter = MagicMock()
        mock_adapter.fetch_catalogue = MagicMock(side_effect=RuntimeError("network error"))

        with patch("src.orchestrator.functions._get_adapter", return_value=mock_adapter):
            with pytest.raises(RuntimeError, match="network error"):
                await harvest_portal(
                    portal_id="statistics_finland",
                    run_id="run-002",
                    db_url=None,
                )


class TestEmbedderCoverage:
    @pytest.mark.asyncio
    async def test_embed_record_calls_embedder(self):
        from src.orchestrator.functions import embed_record
        import respx, httpx

        mvm_dict = {**VALID_MVM_DICT}
        fake_embedding = [0.1] * 1024

        with respx.mock:
            respx.post("http://embedder-test/embed").mock(
                return_value=httpx.Response(200, json={"data": [{"embedding": fake_embedding}]})
            )
            config = {"endpoint_url": "http://embedder-test/embed", "expected_dim": 1024}
            result = await embed_record(mvm_dict=mvm_dict, run_id="run-1", portal_id="statistics_finland", embedder_config=config)

        assert "embedding" in result
        assert len(result["embedding"]) == 1024
