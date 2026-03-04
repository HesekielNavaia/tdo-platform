"""
Unit tests for the Indexer.
Uses an in-memory SQLite database to avoid needing PostgreSQL/testcontainers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.mvm import MVMRecord
from src.pipeline.indexer import Indexer


VALID_RECORD = MVMRecord(
    id="test-uuid-indexer-001",
    source_id="src-indexer-001",
    title="Test Dataset for Indexer",
    publisher="Statistics Finland",
    publisher_type="NSO",
    source_portal="statistics_finland",
    access_type="open",
    metadata_standard="SDMX",
    confidence_score=0.85,
    completeness_score=0.75,
    freshness_score=0.9,
    ingestion_timestamp=datetime.now(timezone.utc),
    keywords=["test", "data"],
    geographic_coverage=["FI"],
)

EMBEDDING = [0.1] * 1024


class TestIndexerUnit:
    """Unit tests using mocked database session."""

    def test_record_to_params_includes_embedding(self):
        indexer = Indexer("postgresql+asyncpg://localhost/test")
        params = indexer._record_to_params(VALID_RECORD, EMBEDDING)
        assert "embedding" in params
        # embedding should be JSON-serialisable
        parsed = json.loads(params["embedding"])
        assert len(parsed) == 1024

    def test_record_to_params_maps_all_fields(self):
        indexer = Indexer("postgresql+asyncpg://localhost/test")
        params = indexer._record_to_params(VALID_RECORD, EMBEDDING)
        assert params["title"] == "Test Dataset for Indexer"
        assert params["publisher"] == "Statistics Finland"
        assert params["confidence_score"] == 0.85
        assert params["keywords"] == ["test", "data"]
        assert params["geographic_coverage"] == ["FI"]

    def test_record_to_params_handles_none_lists(self):
        """None list fields should default to empty lists."""
        record = MVMRecord(
            id="sparse-001",
            source_id="src-sparse",
            title="Sparse",
            publisher="Test",
            publisher_type="other",
            source_portal="test_portal",
            access_type="open",
            metadata_standard="unknown",
            confidence_score=0.1,
            completeness_score=0.1,
            freshness_score=0.5,
            ingestion_timestamp=datetime.now(timezone.utc),
        )
        indexer = Indexer("postgresql+asyncpg://localhost/test")
        params = indexer._record_to_params(record, [])
        assert params["keywords"] == []
        assert params["themes"] == []
        assert params["geographic_coverage"] == []
        assert params["formats"] == []
        assert params["languages"] == []


class TestIndexerMocked:
    """Tests using a mocked SQLAlchemy session to avoid DB dependency."""

    @pytest.mark.asyncio
    async def test_upsert_calls_insert_for_new_record(self):
        indexer = Indexer("postgresql+asyncpg://localhost/test")

        # Mock the session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=None),
            scalar=MagicMock(return_value=1),
        ))
        mock_session.begin = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=None),
        ))

        mock_sessionmaker = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        ))

        with patch.object(indexer, '_sessionmaker', mock_sessionmaker):
            result = await indexer.upsert(VALID_RECORD, EMBEDDING)

        assert result is not None
        assert isinstance(result, str)
