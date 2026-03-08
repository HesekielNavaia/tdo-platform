"""
Indexer — upserts MVM records and embeddings into PostgreSQL.
Handles versioning, alias resolution, and pipeline_runs state tracking.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models.mvm import MVMRecord

log = structlog.get_logger(__name__)


class Indexer:
    def __init__(self, database_url: str):
        self._engine = create_async_engine(database_url, echo=False)
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    async def upsert(
        self,
        record: MVMRecord,
        embedding: list[float],
        pipeline_run_id: str | None = None,
    ) -> str:
        """
        Upsert an MVM record with its embedding into the datasets table.
        Also writes a new row to dataset_versions.
        Returns the canonical dataset ID.
        """
        async with self._sessionmaker() as session:
            async with session.begin():
                # Check for alias (source_id may have changed)
                canonical_id = await self._resolve_alias(session, record)

                if canonical_id:
                    # Update existing record
                    dataset_id = canonical_id
                    await self._update_dataset(session, dataset_id, record, embedding)
                else:
                    # Insert new record
                    dataset_id = str(record.id)
                    await self._insert_dataset(session, dataset_id, record, embedding)
                    # Record current source_id as an alias for lineage
                    await self._register_alias(session, record.source_id, record.source_portal, dataset_id)

                # Write version snapshot
                version_number = await self._get_next_version_number(session, dataset_id)
                version_id = str(uuid4())
                await session.execute(
                    text("""
                        INSERT INTO dataset_versions
                            (id, dataset_id, version_number, mvm_snapshot, pipeline_run_id, created_at)
                        VALUES
                            (:id, :dataset_id, :version_number, :mvm_snapshot, :pipeline_run_id, :created_at)
                    """),
                    {
                        "id": version_id,
                        "dataset_id": dataset_id,
                        "version_number": version_number,
                        "mvm_snapshot": json.dumps(record.model_dump(mode="json"), default=str),
                        "pipeline_run_id": pipeline_run_id,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

                # Update current_version_id pointer
                await session.execute(
                    text("UPDATE datasets SET current_version_id = :vid WHERE id = :did"),
                    {"vid": version_id, "did": dataset_id}
                )

                # Update pipeline_runs if run_id provided
                if pipeline_run_id:
                    await self._update_pipeline_run(session, pipeline_run_id, record.source_id)

                return dataset_id

    async def _resolve_alias(
        self, session: AsyncSession, record: MVMRecord
    ) -> str | None:
        """Check if this source_id has an existing alias → canonical ID."""
        result = await session.execute(
            text("""
                SELECT canonical_id FROM dataset_aliases
                WHERE alias_source_id = :source_id AND portal_id = :portal_id
            """),
            {"source_id": record.source_id, "portal_id": record.source_portal},
        )
        row = result.fetchone()
        if row:
            return str(row[0])

        # Also check datasets table for existing match
        result2 = await session.execute(
            text("""
                SELECT id FROM datasets
                WHERE source_id = :source_id AND portal_id = :portal_id
            """),
            {"source_id": record.source_id, "portal_id": record.source_portal},
        )
        row2 = result2.fetchone()
        if row2:
            return str(row2[0])

        return None

    async def _insert_dataset(
        self,
        session: AsyncSession,
        dataset_id: str,
        record: MVMRecord,
        embedding: list[float],
    ) -> None:
        await session.execute(
            text("""
                INSERT INTO datasets (
                    id, source_id, portal_id, resource_type, title, description,
                    publisher, publisher_type, source_portal, dataset_url,
                    keywords, themes, geographic_coverage, temporal_coverage_start,
                    temporal_coverage_end, languages, update_frequency, last_updated,
                    access_type, access_conditions, license, formats, contact_point,
                    provenance, metadata_standard, confidence_score, completeness_score,
                    freshness_score, link_healthy, ingestion_timestamp, embedding, embedding_vec
                ) VALUES (
                    :id, :source_id, :portal_id, :resource_type, :title, :description,
                    :publisher, :publisher_type, :source_portal, :dataset_url,
                    :keywords, :themes, :geographic_coverage, :temporal_coverage_start,
                    :temporal_coverage_end, :languages, :update_frequency, :last_updated,
                    :access_type, :access_conditions, :license, :formats, :contact_point,
                    :provenance, :metadata_standard, :confidence_score, :completeness_score,
                    :freshness_score, :link_healthy, :ingestion_timestamp, :embedding,
                    CAST(:embedding AS vector)
                )
            """),
            {
                "id": dataset_id,
                "source_id": record.source_id,
                "portal_id": record.source_portal,
                **self._record_to_params(record, embedding),
            }
        )

    async def _update_dataset(
        self,
        session: AsyncSession,
        dataset_id: str,
        record: MVMRecord,
        embedding: list[float],
    ) -> None:
        params = self._record_to_params(record, embedding)
        params["id"] = dataset_id
        await session.execute(
            text("""
                UPDATE datasets SET
                    resource_type = :resource_type,
                    title = :title,
                    description = :description,
                    publisher = :publisher,
                    publisher_type = :publisher_type,
                    dataset_url = :dataset_url,
                    keywords = :keywords,
                    themes = :themes,
                    geographic_coverage = :geographic_coverage,
                    temporal_coverage_start = :temporal_coverage_start,
                    temporal_coverage_end = :temporal_coverage_end,
                    languages = :languages,
                    update_frequency = :update_frequency,
                    last_updated = :last_updated,
                    access_type = :access_type,
                    access_conditions = :access_conditions,
                    license = :license,
                    formats = :formats,
                    contact_point = :contact_point,
                    provenance = :provenance,
                    metadata_standard = :metadata_standard,
                    confidence_score = :confidence_score,
                    completeness_score = :completeness_score,
                    freshness_score = :freshness_score,
                    link_healthy = :link_healthy,
                    ingestion_timestamp = :ingestion_timestamp,
                    embedding = :embedding,
                    embedding_vec = CAST(:embedding AS vector)
                WHERE id = :id
            """),
            params
        )

    async def _register_alias(
        self,
        session: AsyncSession,
        source_id: str,
        portal_id: str,
        canonical_id: str,
    ) -> None:
        await session.execute(
            text("""
                INSERT INTO dataset_aliases (alias_source_id, portal_id, canonical_id, first_seen)
                VALUES (:source_id, :portal_id, :canonical_id, :first_seen)
                ON CONFLICT (alias_source_id, portal_id) DO NOTHING
            """),
            {
                "source_id": source_id,
                "portal_id": portal_id,
                "canonical_id": canonical_id,
                "first_seen": datetime.now(timezone.utc),
            }
        )

    async def _get_next_version_number(
        self, session: AsyncSession, dataset_id: str
    ) -> int:
        result = await session.execute(
            text("""
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM dataset_versions WHERE dataset_id = :did
            """),
            {"did": dataset_id}
        )
        return result.scalar() or 1

    async def _update_pipeline_run(
        self, session: AsyncSession, run_id: str, source_id: str
    ) -> None:
        await session.execute(
            text("""
                UPDATE pipeline_runs
                SET status = 'complete', completed_at = :now, source_id = :source_id
                WHERE run_id = :run_id
            """),
            {"now": datetime.now(timezone.utc), "source_id": source_id, "run_id": run_id}
        )

    def _record_to_params(
        self, record: MVMRecord, embedding: list[float]
    ) -> dict:
        return {
            "resource_type": record.resource_type,
            "title": record.title,
            "description": record.description,
            "publisher": record.publisher,
            "publisher_type": record.publisher_type,
            "source_portal": record.source_portal,
            "dataset_url": record.dataset_url,
            "keywords": record.keywords or [],
            "themes": record.themes or [],
            "geographic_coverage": record.geographic_coverage or [],
            "temporal_coverage_start": record.temporal_coverage_start,
            "temporal_coverage_end": record.temporal_coverage_end,
            "languages": record.languages or [],
            "update_frequency": record.update_frequency,
            "last_updated": record.last_updated,
            "access_type": record.access_type,
            "access_conditions": record.access_conditions,
            "license": record.license,
            "formats": record.formats or [],
            "contact_point": record.contact_point,
            "provenance": record.provenance,
            "metadata_standard": record.metadata_standard,
            "confidence_score": record.confidence_score,
            "completeness_score": record.completeness_score,
            "freshness_score": record.freshness_score,
            "link_healthy": record.link_healthy,
            "ingestion_timestamp": record.ingestion_timestamp,
            "embedding": json.dumps(embedding),
        }
