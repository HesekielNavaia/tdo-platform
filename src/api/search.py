"""
Hybrid search implementation using RRF (Reciprocal Rank Fusion)
over pgvector cosine similarity and PostgreSQL tsvector full-text search.
"""
from __future__ import annotations

import structlog
from typing import Any

from src.models.mvm import MVMRecord, SearchFilters, SearchResult

log = structlog.get_logger(__name__)

RRF_K = 60  # RRF constant


def compute_rrf_score(rank: int, k: int = RRF_K) -> float:
    """RRF score = 1 / (k + rank), where rank is 1-based."""
    return 1.0 / (k + rank)


def rrf_fusion(
    semantic_results: list[tuple[str, float]],  # (id, score) ranked list
    keyword_results: list[tuple[str, float]],   # (id, score) ranked list
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[tuple[str, float]]:
    """
    Combine two ranked lists using Reciprocal Rank Fusion.
    Returns sorted list of (id, combined_score).
    """
    scores: dict[str, float] = {}

    for rank, (doc_id, _) in enumerate(semantic_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + semantic_weight * compute_rrf_score(rank)

    for rank, (doc_id, _) in enumerate(keyword_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + keyword_weight * compute_rrf_score(rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def build_filter_clause(filters: SearchFilters) -> tuple[str, dict[str, Any]]:
    """Build a SQL WHERE clause from SearchFilters. Returns (clause, params)."""
    conditions = []
    params: dict[str, Any] = {}

    params["min_confidence"] = filters.min_confidence
    conditions.append("confidence_score >= :min_confidence")

    if filters.geo:
        params["geo"] = filters.geo
        conditions.append("geographic_coverage && :geo")

    if filters.theme:
        params["theme"] = filters.theme
        conditions.append("themes && :theme")

    if filters.publisher:
        params["publisher"] = f"%{filters.publisher}%"
        conditions.append("publisher ILIKE :publisher")

    if filters.format:
        params["format"] = [filters.format]
        conditions.append("formats && :format")

    if filters.access:
        params["access"] = filters.access
        conditions.append("access_type = :access")

    if filters.resource_type:
        params["resource_type"] = filters.resource_type
        conditions.append("resource_type = :resource_type")

    if filters.updated_after:
        params["updated_after"] = filters.updated_after
        conditions.append("last_updated >= :updated_after")

    clause = " AND ".join(conditions) if conditions else "TRUE"
    return clause, params


class HybridSearch:
    """
    Hybrid search engine combining pgvector semantic search with
    PostgreSQL tsvector keyword search via RRF.
    """

    def __init__(self, db_session_factory, embedder=None):
        self._session_factory = db_session_factory
        self._embedder = embedder

    async def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 20,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[SearchResult]:
        """
        Hybrid search: embed query → pgvector + tsvector → RRF fusion.
        """
        filters = filters or SearchFilters()
        filter_clause, filter_params = build_filter_clause(filters)

        semantic_results: list[tuple[str, float]] = []
        keyword_results: list[tuple[str, float]] = []
        search_channel = "hybrid"

        async with self._session_factory() as session:
            # Semantic search (if embedder available and query provided)
            if self._embedder and query:
                from src.models.mvm import MVMRecord as _MVMRecord
                try:
                    # Build a minimal record just for the embedding input
                    query_embedding = await self._embedder._call_endpoint([query])
                    if query_embedding:
                        vec = query_embedding[0]
                        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
                        from sqlalchemy import text
                        sem_rows = await session.execute(
                            text(f"""
                                SELECT id, (embedding::vector <=> :vec::vector) AS distance
                                FROM datasets
                                WHERE {filter_clause}
                                ORDER BY distance ASC
                                LIMIT :limit
                            """),
                            {**filter_params, "vec": vec_str, "limit": limit * 2}
                        )
                        semantic_results = [
                            (str(row[0]), 1.0 - float(row[1])) for row in sem_rows
                        ]
                except Exception as e:
                    log.warning("semantic_search_failed", error=str(e))

            # Keyword search (always run if query provided)
            if query:
                from sqlalchemy import text
                kw_rows = await session.execute(
                    text(f"""
                        SELECT id, ts_rank_cd(fts_en, plainto_tsquery('simple', :query)) AS rank
                        FROM datasets
                        WHERE {filter_clause}
                          AND fts_en @@ plainto_tsquery('simple', :query)
                        ORDER BY rank DESC
                        LIMIT :limit
                    """),
                    {**filter_params, "query": query, "limit": limit * 2}
                )
                keyword_results = [(str(row[0]), float(row[1])) for row in kw_rows]

            # Handle edge cases: only one channel has results
            if semantic_results and not keyword_results:
                search_channel = "semantic"
                combined = [(doc_id, score) for doc_id, score in semantic_results[:limit]]
                log.info("search_single_channel", channel="semantic")
            elif keyword_results and not semantic_results:
                search_channel = "keyword"
                combined = [(doc_id, score) for doc_id, score in keyword_results[:limit]]
                log.info("search_single_channel", channel="keyword")
            elif not semantic_results and not keyword_results:
                # Filter-only query or no results
                from sqlalchemy import text
                filter_rows = await session.execute(
                    text(f"""
                        SELECT id, confidence_score FROM datasets
                        WHERE {filter_clause}
                        ORDER BY confidence_score DESC
                        LIMIT :limit OFFSET :offset
                    """),
                    {**filter_params, "limit": limit, "offset": filters.offset}
                )
                combined = [(str(row[0]), float(row[1])) for row in filter_rows]
                search_channel = "filter"
            else:
                # Full hybrid RRF
                combined = rrf_fusion(
                    semantic_results, keyword_results, semantic_weight, keyword_weight
                )[:limit]

            # Fetch full records for top results
            if not combined:
                return []

            result_ids = [doc_id for doc_id, _ in combined]
            id_to_score = {doc_id: score for doc_id, score in combined}

            from sqlalchemy import text
            rows = await session.execute(
                text("""
                    SELECT id, source_id, portal_id, resource_type, title, description,
                           publisher, publisher_type, source_portal, dataset_url,
                           keywords, themes, geographic_coverage, temporal_coverage_start,
                           temporal_coverage_end, languages, update_frequency, last_updated,
                           access_type, access_conditions, license, formats, contact_point,
                           provenance, metadata_standard, confidence_score, completeness_score,
                           freshness_score, link_healthy, ingestion_timestamp
                    FROM datasets
                    WHERE id = ANY(:ids)
                """),
                {"ids": result_ids}
            )

            results = []
            for row in rows:
                try:
                    record = self._row_to_mvm(row)
                    score = id_to_score.get(str(row[0]), 0.0)
                    results.append(SearchResult(
                        record=record,
                        similarity_score=min(1.0, max(0.0, score)),
                        search_channel=search_channel,
                    ))
                except Exception as e:
                    log.error("row_to_mvm_failed", error=str(e))

            # Sort by score descending, preserving RRF order
            results.sort(key=lambda r: id_to_score.get(str(r.record.id), 0.0), reverse=True)
            return results

    def _row_to_mvm(self, row) -> MVMRecord:
        """Convert a DB row tuple to an MVMRecord."""
        from datetime import datetime, timezone

        def safe_list(val) -> list:
            if val is None:
                return []
            if isinstance(val, list):
                return val
            return []

        def safe_ts(val):
            if val is None:
                return datetime.now(timezone.utc)
            if isinstance(val, datetime):
                return val
            return datetime.now(timezone.utc)

        return MVMRecord(
            id=str(row[0]),
            source_id=str(row[1]),
            source_id_aliases=[],
            resource_type=str(row[3]) if row[3] else "dataset",
            title=str(row[4]) if row[4] else "Untitled",
            description=row[5],
            publisher=str(row[6]) if row[6] else "Unknown",
            publisher_type=str(row[7]) if row[7] else "other",
            source_portal=str(row[8]) if row[8] else "",
            dataset_url=row[9],
            keywords=safe_list(row[10]),
            themes=safe_list(row[11]),
            geographic_coverage=safe_list(row[12]),
            temporal_coverage_start=row[13],
            temporal_coverage_end=row[14],
            languages=safe_list(row[15]),
            update_frequency=row[16],
            last_updated=row[17],
            access_type=str(row[18]) if row[18] else "open",
            access_conditions=row[19],
            license=row[20],
            formats=safe_list(row[21]),
            contact_point=row[22],
            provenance=row[23],
            metadata_standard=str(row[24]) if row[24] else "unknown",
            confidence_score=float(row[25]) if row[25] is not None else 0.0,
            completeness_score=float(row[26]) if row[26] is not None else 0.0,
            freshness_score=float(row[27]) if row[27] is not None else 0.5,
            link_healthy=row[28],
            ingestion_timestamp=safe_ts(row[29]),
        )
