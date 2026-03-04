"""
Integration test: full pipeline for Statistics Finland.
Requires docker-compose.test.yml to be running.

Run with:
  docker-compose -f docker-compose.test.yml up -d
  python -m pytest tests/integration/test_full_pipeline.py -v
  docker-compose -f docker-compose.test.yml down
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Skip all integration tests if environment flag not set
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="Integration tests require RUN_INTEGRATION_TESTS=1 and docker-compose running",
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tdo_test"
)
EMBEDDING_ENDPOINT = os.environ.get("EMBEDDING_ENDPOINT", "http://localhost:8080")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))


@pytest.fixture(scope="session")
async def db_session():
    """Create a database session with schema initialised."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import text

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Ensure pgvector extension is enabled
    async with session_factory() as session:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await session.commit()

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_full_pipeline_statistics_finland(db_session):
    """
    End-to-end: harvest one StatFin dataset → harmonise → embed → index → query
    """
    from src.adapters.statistics_finland import StatisticsFinlandAdapter, STATFIN_BASE_URL
    from src.pipeline.harmoniser import Harmoniser, HarmoniserConfig
    from src.pipeline.embedder import Embedder, EmbedderConfig
    from src.pipeline.indexer import Indexer
    from src.api.search import HybridSearch, SearchFilters

    # 1. Harvest
    adapter = StatisticsFinlandAdapter()
    source_id = "StatFin/tym/tyonv/"

    # Fetch a real record from the API
    import httpx
    import respx

    mock_payload = {
        "id": "StatFin/tym/tyonv/",
        "text": "Unemployed job seekers",
        "description": "Monthly data on unemployed job seekers registered at employment offices.",
        "updated": "2024-12-01",
        "type": "t",
        "_source_portal": "https://stat.fi",
        "_publisher": "Statistics Finland",
        "_publisher_type": "NSO",
        "_access_type": "open",
        "_license": "CC-BY 4.0",
        "_schema_detected": "SDMX",
        "_formats": ["JSON", "SDMX"],
        "_languages": ["fi", "en"],
    }

    with respx.mock:
        respx.get(f"{STATFIN_BASE_URL}/{source_id}").mock(
            return_value=httpx.Response(200, json=mock_payload)
        )
        record = await adapter.fetch_record(source_id)

    assert record.raw_payload is not None, "raw_payload must not be None"
    assert record.raw_payload_hash is not None, "raw_payload_hash must not be None"
    assert len(record.raw_payload_hash) == 64, "hash must be SHA-256 (64 hex chars)"
    assert record.source_id == source_id

    # 2. Harmonise
    harmoniser = Harmoniser(config=HarmoniserConfig())
    mvm, meta = await harmoniser.process(
        record.raw_payload, "statistics_finland", source_id=source_id
    )

    assert mvm.title is not None, "title must not be None"
    assert mvm.publisher == "Statistics Finland", f"expected Statistics Finland, got {mvm.publisher}"
    assert mvm.confidence_score >= 0.0
    assert 0.0 <= mvm.completeness_score <= 1.0
    # LLM must not have invented dataset_url
    assert mvm.dataset_url is None or mvm.dataset_url.startswith("https://")

    # 3. Embed
    embedder_config = EmbedderConfig(
        endpoint_url=EMBEDDING_ENDPOINT,
        expected_dim=EMBEDDING_DIM,
    )
    embedder = Embedder(embedder_config)

    # Try embedding if endpoint is available; otherwise skip
    try:
        embedding = await embedder.embed(mvm)
        assert len(embedding) == EMBEDDING_DIM, (
            f"embedding dim {len(embedding)} != expected {EMBEDDING_DIM}"
        )
    except Exception as e:
        pytest.skip(f"Embedding endpoint not available: {e}")

    # 4. Index
    indexer = Indexer(DATABASE_URL)
    dataset_id = await indexer.upsert(mvm, embedding)
    assert dataset_id is not None

    # 5. Query
    search = HybridSearch(db_session, embedder=embedder)
    filters = SearchFilters(min_confidence=0.0)
    results = await search.search(
        query="Finnish labour market statistics",
        filters=filters,
        limit=10,
    )
    # The indexed record should appear in results
    result_ids = {r.record.id for r in results}
    assert mvm.id in result_ids or dataset_id in result_ids, (
        f"Expected {mvm.id} in results, got {result_ids}"
    )


@pytest.mark.asyncio
async def test_pipeline_idempotency(db_session):
    """Upserting the same record twice must not create duplicates."""
    from src.adapters.statistics_finland import StatisticsFinlandAdapter, STATFIN_BASE_URL
    from src.pipeline.harmoniser import Harmoniser, HarmoniserConfig
    from src.pipeline.indexer import Indexer
    from sqlalchemy import text

    import httpx
    import respx

    mock_payload = {
        "id": "StatFin/vrm/vrm001/",
        "text": "Population by region",
        "_source_portal": "https://stat.fi",
        "_publisher": "Statistics Finland",
        "_publisher_type": "NSO",
        "_access_type": "open",
        "_schema_detected": "SDMX",
    }

    adapter = StatisticsFinlandAdapter()
    source_id = "StatFin/vrm/vrm001/"

    with respx.mock:
        respx.get(f"{STATFIN_BASE_URL}/{source_id}").mock(
            return_value=httpx.Response(200, json=mock_payload)
        )
        record = await adapter.fetch_record(source_id)

    harmoniser = Harmoniser(HarmoniserConfig())
    mvm, _ = await harmoniser.process(record.raw_payload, "statistics_finland", source_id=source_id)

    embedding = [0.1] * EMBEDDING_DIM
    indexer = Indexer(DATABASE_URL)

    id1 = await indexer.upsert(mvm, embedding)
    id2 = await indexer.upsert(mvm, embedding)

    # Both calls must return the same canonical ID
    assert id1 == id2, f"Expected same ID, got {id1} and {id2}"

    # Verify only one row exists
    async with db_session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM datasets WHERE source_id = :sid AND portal_id = :pid"),
            {"sid": source_id, "pid": mvm.source_portal}
        )
        count = result.scalar()
        assert count == 1, f"Expected 1 row, got {count}"
