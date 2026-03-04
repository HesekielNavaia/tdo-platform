"""
Unit tests for the Embedder.
Uses respx to mock the embedding endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import respx
import httpx

from src.models.mvm import MVMRecord
from src.pipeline.embedder import Embedder, EmbedderConfig, ConfigurationError

EMBEDDING_ENDPOINT = "http://embeddings:80/embed"

VALID_RECORD = MVMRecord(
    id="test-001",
    source_id="src-001",
    title="Finnish Labour Market Statistics",
    description="Monthly data on unemployment in Finland",
    publisher="Statistics Finland",
    publisher_type="NSO",
    source_portal="https://stat.fi",
    access_type="open",
    metadata_standard="SDMX",
    confidence_score=0.9,
    completeness_score=0.8,
    freshness_score=0.7,
    keywords=["unemployment", "labour", "Finland"],
    themes=["employment"],
    geographic_coverage=["FI"],
    ingestion_timestamp=datetime.now(timezone.utc),
)


def make_config(dim: int = 1024) -> EmbedderConfig:
    return EmbedderConfig(
        endpoint_url=EMBEDDING_ENDPOINT,
        model_id="multilingual-e5-large",
        expected_dim=dim,
    )


def make_embedding_response(dim: int = 1024) -> dict:
    return {
        "data": [{"embedding": [0.1] * dim, "index": 0}],
        "model": "multilingual-e5-large",
    }


class TestEmbedder:
    @pytest.mark.asyncio
    async def test_validate_config_passes_on_correct_dim(self):
        config = make_config(dim=1024)
        embedder = Embedder(config)

        with respx.mock:
            respx.post(EMBEDDING_ENDPOINT).mock(
                return_value=httpx.Response(200, json=make_embedding_response(1024))
            )
            result = await embedder.validate_config()

        assert result == 1024

    @pytest.mark.asyncio
    async def test_validate_config_raises_on_dim_mismatch(self):
        config = make_config(dim=768)  # Configured for 768 but endpoint returns 1024
        embedder = Embedder(config)

        with respx.mock:
            respx.post(EMBEDDING_ENDPOINT).mock(
                return_value=httpx.Response(200, json=make_embedding_response(1024))
            )
            with pytest.raises(ConfigurationError) as exc_info:
                await embedder.validate_config()

        assert "768" in str(exc_info.value)
        assert "1024" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_embed_returns_list_of_floats(self):
        config = make_config()
        embedder = Embedder(config)

        with respx.mock:
            respx.post(EMBEDDING_ENDPOINT).mock(
                return_value=httpx.Response(200, json=make_embedding_response(1024))
            )
            result = await embedder.embed(VALID_RECORD)

        assert isinstance(result, list)
        assert len(result) == 1024
        assert all(isinstance(v, float) for v in result)

    def test_build_embedding_input_includes_all_fields(self):
        config = make_config()
        embedder = Embedder(config)
        input_text = embedder._build_embedding_input(VALID_RECORD)

        assert "Finnish Labour Market Statistics" in input_text
        assert "Monthly data on unemployment" in input_text
        assert "unemployment" in input_text
        assert "Finland" in input_text
        assert "Statistics Finland" in input_text
        assert "FI" in input_text

    def test_build_embedding_input_handles_empty_fields(self):
        config = make_config()
        embedder = Embedder(config)
        sparse_record = MVMRecord(
            id="sparse-001",
            source_id="src-sparse",
            title="Sparse Record",
            publisher="Test",
            publisher_type="other",
            source_portal="https://example.com",
            access_type="open",
            metadata_standard="unknown",
            confidence_score=0.3,
            completeness_score=0.1,
            freshness_score=0.5,
            ingestion_timestamp=datetime.now(timezone.utc),
        )
        input_text = embedder._build_embedding_input(sparse_record)
        assert "Sparse Record" in input_text
        assert "Test" in input_text

    @pytest.mark.asyncio
    async def test_embed_uses_correct_input_string(self):
        config = make_config()
        embedder = Embedder(config)
        captured_requests = []

        with respx.mock:
            def capture(request):
                captured_requests.append(request)
                return httpx.Response(200, json=make_embedding_response(1024))

            respx.post(EMBEDDING_ENDPOINT).mock(side_effect=capture)
            await embedder.embed(VALID_RECORD)

        assert len(captured_requests) == 1
        import json
        body = json.loads(captured_requests[0].content)
        assert "input" in body
        assert len(body["input"]) == 1
        assert "Finnish Labour Market Statistics" in body["input"][0]

    @pytest.mark.asyncio
    async def test_tei_format_response_also_works(self):
        """Test HuggingFace TEI format: list of lists."""
        config = make_config()
        embedder = Embedder(config)

        tei_response = [[0.5] * 1024]

        with respx.mock:
            respx.post(EMBEDDING_ENDPOINT).mock(
                return_value=httpx.Response(200, json=tei_response)
            )
            result = await embedder.embed(VALID_RECORD)

        assert len(result) == 1024
